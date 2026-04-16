param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,

    [string]$WorkspaceRoot = "E:\web\plc-workspace",

    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"

function Invoke-CapturedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = "",
        [int]$TimeoutSeconds = 120
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = ($Arguments -join " ")
    if ($WorkingDirectory) {
        $psi.WorkingDirectory = $WorkingDirectory
    }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    $null = $process.Start()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            $process.Kill()
        }
        catch {
        }
        $stdoutTimeout = $process.StandardOutput.ReadToEnd()
        $stderrTimeout = $process.StandardError.ReadToEnd()
        $process.Dispose()

        return [pscustomobject]@{
            ExitCode = -1
            Output = (($stdoutTimeout + "`r`n" + $stderrTimeout).Trim() + "`r`n[timeout after $TimeoutSeconds seconds]").Trim()
        }
    }
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $exitCode = $process.ExitCode
    $process.Dispose()

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($stdout + "`r`n" + $stderr).Trim()
    }
}

$reportDir = Join-Path $ProjectPath "04_reports\modelcheck"
$sourceDir = Join-Path $ProjectPath "02_src\st"
$propertyFile = Join-Path $ProjectPath "01_specs\properties.md"
$plcrexDir = Join-Path $ProjectPath "03_checks\plcrex"

if (-not $ConfigPath) {
    $ConfigPath = $env:PLC_WORKSPACE_TOOLCHAIN_CONFIG
}

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $WorkspaceRoot "validation\config\toolchain.local.json"
}

if (-not (Test-Path -LiteralPath $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir | Out-Null
}

if (-not (Test-Path -LiteralPath $sourceDir)) {
    throw "missing source dir: $sourceDir"
}

if (-not (Test-Path -LiteralPath $propertyFile)) {
    throw "missing properties file: $propertyFile"
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "missing toolchain config: $ConfigPath"
}

$config = Get-Content -Raw $ConfigPath | ConvertFrom-Json
$py39 = $config.py39
$plcrexCliScript = $config.plcrex_cli_script
$plcverifCliDir = $config.plcverif_cli_dir
$sourceFile = Get-ChildItem -LiteralPath $sourceDir -Filter "*.st" | Select-Object -First 1
$plcverifCliExe = $config.plcverif_entry
$plcverifToolsDir = $config.plcverif_tools_dir
$plcverifDemoProjectDir = $config.plcverif_demo_project_dir
$plcverifDemoCase = $config.plcverif_demo_case
$plcverifBackendBinary = $config.plcverif_backend_binary
$projectPlcverifDir = Join-Path $ProjectPath "03_checks\plcverif"
$projectPlcverifCase = $null
$projectPlcverifRun = $null
$projectPlcverifReady = $false
$projectPlcverifCexPath = $null
$projectPlcverifCexResult = "not_generated"
$plcverifHelpRun = $null
$plcverifDemoRun = $null
$plcverifHelpReady = $false
$plcverifDemoReady = $false
$plcverifDemoCexPath = $null
$plcverifDemoCexResult = "not_generated"
$plcverifStatus = @()

if (-not $sourceFile) {
    throw "no .st source found in: $sourceDir"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$summaryFile = Join-Path $reportDir ("modelcheck-gate-" + $timestamp + ".md")
$parserExport = Join-Path $plcrexDir ("model-parser-" + $timestamp)
$parserArgs = @()
if ($plcrexCliScript) {
    $parserArgs += @($plcrexCliScript, "st-parser")
}
else {
    $parserArgs += @("-m", "plcrex", "st-parser")
}
$parserArgs += @(('"' + $sourceFile.FullName + '"'), ('"' + $parserExport + '"'))

$parserRun = Invoke-CapturedProcess -FilePath $py39 -Arguments $parserArgs
$parserOutput = $parserRun.Output
$parserExit = $parserRun.ExitCode

$propertyLines = Get-Content -Encoding UTF8 $propertyFile
$propertyCount = ($propertyLines | Where-Object { $_ -match '^## P[0-9]+' }).Count

if ($plcverifCliDir) {
    if (-not $plcverifCliExe) {
        $plcverifCliExe = Join-Path $plcverifCliDir "eclipsec.exe"
    }
    if (-not $plcverifToolsDir) {
        $plcverifToolsDir = Join-Path (Split-Path -Parent $plcverifCliDir) "tools"
    }
    if (-not $plcverifDemoProjectDir) {
        $plcverifDemoProjectDir = Join-Path $plcverifToolsDir "workspace\DemoProject"
    }
    if (-not $plcverifDemoCase) {
        $plcverifDemoCase = Join-Path $plcverifDemoProjectDir "DemoCase-assert-nusmv.vc3"
    }
    if (-not $plcverifBackendBinary) {
        $plcverifBackendBinary = Join-Path $plcverifToolsDir "tools\nuxmv\nuXmv.exe"
    }
    if (Test-Path -LiteralPath $projectPlcverifDir) {
        $projectPlcverifCase = Get-ChildItem -LiteralPath $projectPlcverifDir -Filter "*.vc3" | Select-Object -First 1 -ExpandProperty FullName
    }

    if (Test-Path -LiteralPath $plcverifCliExe) {
        $plcverifHelpRun = Invoke-CapturedProcess -FilePath $plcverifCliExe -WorkingDirectory $plcverifCliDir -TimeoutSeconds 90 -Arguments @(
            "-nosplash",
            "-consoleLog",
            "-application", "cern.plcverif.cli.cmdline.app.application",
            "-help"
        )
        $plcverifHelpReady = $plcverifHelpRun.Output -match "PERMITTED COMMAND LINE PARAMETERS:"
        if ($plcverifHelpReady) {
            $plcverifStatus += "help probe succeeded"
        }
        else {
            $plcverifStatus += "help probe failed"
        }

        if ($projectPlcverifCase -and (Test-Path -LiteralPath $projectPlcverifCase) -and (Test-Path -LiteralPath $plcverifBackendBinary)) {
            $projectPlcverifRun = Invoke-CapturedProcess -FilePath $plcverifCliExe -WorkingDirectory $projectPlcverifDir -TimeoutSeconds 180 -Arguments @(
                "-nosplash",
                "-consoleLog",
                "-application", "cern.plcverif.cli.cmdline.app.application",
                ('"' + $projectPlcverifCase + '"'),
                "-job.backend.binary_path", ('"' + $plcverifBackendBinary + '"')
            )
            $projectPlcverifReady = $projectPlcverifRun.Output -match "Program directory:" -or $projectPlcverifRun.Output -match "Requirement:"
            $projectPlcverifCexMatch = [regex]::Match($projectPlcverifRun.Output, 'Output to file:\s*(.+?\.cex)')
            if ($projectPlcverifCexMatch.Success) {
                $projectPlcverifCexPath = $projectPlcverifCexMatch.Groups[1].Value.Trim()
                if (Test-Path -LiteralPath $projectPlcverifCexPath) {
                    $projectPlcverifCexText = Get-Content -Raw -LiteralPath $projectPlcverifCexPath
                    if ($projectPlcverifCexText -match 'is true') {
                        $projectPlcverifCexResult = "pass"
                    }
                    elseif ($projectPlcverifCexText -match 'is false') {
                        $projectPlcverifCexResult = "fail"
                    }
                    else {
                        $projectPlcverifCexResult = "unknown"
                    }
                }
            }

            if ($projectPlcverifRun.Output -match "ERROR:  Unable to parse the given settings") {
                $plcverifStatus += "project case parsed CLI but failed on .vc3 or source settings"
            }
            elseif ($projectPlcverifCexResult -eq "pass") {
                $plcverifStatus += "project case assertions passed in generated .cex result"
            }
            elseif ($projectPlcverifCexResult -eq "fail") {
                $plcverifStatus += "project case assertions failed in generated .cex result"
            }
            elseif ($projectPlcverifRun.Output -match "Requirement:") {
                $plcverifStatus += "project case reached verification result stage"
            }
            elseif ($projectPlcverifRun.Output -match "Program directory:") {
                $plcverifStatus += "project case launched PLCverif but did not reach final result text"
            }
            else {
                $plcverifStatus += "project case invocation failed before verification"
            }
        }
        elseif ($projectPlcverifDir) {
            $plcverifStatus += "project case skipped: .vc3 or backend binary missing"
        }

        if ((Test-Path -LiteralPath $plcverifDemoProjectDir) -and
            (Test-Path -LiteralPath $plcverifDemoCase) -and
            (Test-Path -LiteralPath $plcverifBackendBinary)) {
            $plcverifDemoRun = Invoke-CapturedProcess -FilePath $plcverifCliExe -WorkingDirectory $plcverifDemoProjectDir -TimeoutSeconds 120 -Arguments @(
                "-nosplash",
                "-consoleLog",
                "-application", "cern.plcverif.cli.cmdline.app.application",
                ('"' + $plcverifDemoCase + '"'),
                "-job.backend.binary_path", ('"' + $plcverifBackendBinary + '"')
            )
            $plcverifDemoReady = $plcverifDemoRun.Output -match "Program directory:" -or $plcverifDemoRun.Output -match "NuSMV backend"
            $plcverifDemoCexMatch = [regex]::Match($plcverifDemoRun.Output, 'Output to file:\s*(.+?\.cex)')
            if ($plcverifDemoCexMatch.Success) {
                $plcverifDemoCexPath = $plcverifDemoCexMatch.Groups[1].Value.Trim()
                if (Test-Path -LiteralPath $plcverifDemoCexPath) {
                    $plcverifDemoCexText = Get-Content -Raw -LiteralPath $plcverifDemoCexPath
                    if ($plcverifDemoCexText -match 'is true') {
                        $plcverifDemoCexResult = "pass"
                    }
                    elseif ($plcverifDemoCexText -match 'is false') {
                        $plcverifDemoCexResult = "fail"
                    }
                    else {
                        $plcverifDemoCexResult = "unknown"
                    }
                }
            }

            if ($plcverifDemoRun.Output -match "NoClassDefFoundError: javax/xml/bind/JAXBException") {
                $plcverifStatus += "pattern requirement path still needs JAXB-compatible Java runtime"
            }
            if ($plcverifDemoRun.Output -match "NuSMV binary is not found") {
                $plcverifStatus += "backend default path mismatch; override works only when passed explicitly"
            }
            if ($plcverifDemoRun.Output -match "The following value is not preceded by an argument name") {
                $plcverifStatus += "CLI argument formatting still invalid"
            }
            if ($plcverifDemoCexResult -eq "pass") {
                $plcverifStatus += "demo assertion smoke passed"
            }
            elseif ($plcverifDemoCexResult -eq "fail") {
                $plcverifStatus += "demo assertion smoke produced expected failing counterexample"
            }
            elseif ($plcverifDemoReady) {
                $plcverifStatus += "demo assertion smoke reached backend stage"
            }
        }
        else {
            $plcverifStatus += "demo assertion smoke skipped: bundled demo files missing"
        }
    }
    else {
        $plcverifStatus += "configured cli dir does not contain eclipsec.exe"
    }
}
else {
    $plcverifStatus += "plcverif cli dir not configured"
}

$lines = @()
$lines += "# Modelcheck Gate"
$lines += ""
$lines += "- project: $ProjectPath"
$lines += "- checked_at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$lines += "- source_file: $($sourceFile.FullName)"
$lines += "- properties_file: $propertyFile"
$lines += ""
$lines += "## Results"
$lines += ""
$lines += "- parser_exit: $parserExit"
$lines += "- parser_export: $parserExport"
$lines += "- property_count: $propertyCount"
if ($plcverifCliDir) {
    $lines += "- plcverif_cli_dir: $plcverifCliDir"
    $lines += "- plcverif_cli_exe: $plcverifCliExe"
    if ($projectPlcverifCase) {
        $lines += "- plcverif_project_case: $projectPlcverifCase"
    }
    $lines += "- plcverif_demo_case: $plcverifDemoCase"
    $lines += "- plcverif_backend_binary: $plcverifBackendBinary"
}
else {
    $lines += "- plcverif_cli_dir: not configured"
}
$lines += "- plcverif_help_ready: $plcverifHelpReady"
if ($plcverifHelpRun) {
    $lines += "- plcverif_help_exit: $($plcverifHelpRun.ExitCode)"
}
$lines += "- plcverif_project_ready: $projectPlcverifReady"
if ($projectPlcverifRun) {
    $lines += "- plcverif_project_exit: $($projectPlcverifRun.ExitCode)"
}
$lines += "- plcverif_project_cex_result: $projectPlcverifCexResult"
if ($projectPlcverifCexPath) {
    $lines += "- plcverif_project_cex_path: $projectPlcverifCexPath"
}
$lines += "- plcverif_demo_ready: $plcverifDemoReady"
if ($plcverifDemoRun) {
    $lines += "- plcverif_demo_exit: $($plcverifDemoRun.ExitCode)"
}
$lines += "- plcverif_demo_cex_result: $plcverifDemoCexResult"
if ($plcverifDemoCexPath) {
    $lines += "- plcverif_demo_cex_path: $plcverifDemoCexPath"
}
$lines += ""
$lines += "## Properties Snapshot"
$lines += ""
$lines += '```text'
$lines += ($propertyLines -join "`r`n")
$lines += '```'
$lines += ""
$lines += "## Parser Output"
$lines += ""
$lines += '```text'
$lines += $parserOutput.Trim()
$lines += '```'
$lines += ""
$lines += "## PLCverif Status"
$lines += ""
foreach ($statusLine in $plcverifStatus) {
    $lines += "- $statusLine"
}
if ($plcverifHelpRun) {
    $lines += ""
    $lines += "## PLCverif Help Output"
    $lines += ""
    $lines += '```text'
    $lines += $plcverifHelpRun.Output.Trim()
    $lines += '```'
}
if ($projectPlcverifRun) {
    $lines += ""
    $lines += "## PLCverif Project Case"
    $lines += ""
    $lines += '```text'
    $lines += $projectPlcverifRun.Output.Trim()
    $lines += '```'
}
if ($plcverifDemoRun) {
    $lines += ""
    $lines += "## PLCverif Demo Assertion Smoke"
    $lines += ""
    $lines += '```text'
    $lines += $plcverifDemoRun.Output.Trim()
    $lines += '```'
}

Set-Content -LiteralPath $summaryFile -Value ($lines -join "`r`n") -Encoding UTF8
Write-Output "Wrote: $summaryFile"
