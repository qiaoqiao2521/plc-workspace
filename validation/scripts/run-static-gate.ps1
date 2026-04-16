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
        [string[]]$Arguments
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = ($Arguments -join " ")
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    $null = $process.Start()
    $process.WaitForExit()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $exitCode = $process.ExitCode
    $process.Dispose()

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($stdout + "`r`n" + $stderr).Trim()
    }
}

$sourceDir = Join-Path $ProjectPath "02_src\st"
$reportDir = Join-Path $ProjectPath "04_reports\static"
$plcrexDir = Join-Path $ProjectPath "03_checks\plcrex"
$iecDir = Join-Path $ProjectPath "03_checks\iec-checker"

if (-not $ConfigPath) {
    $ConfigPath = $env:PLC_WORKSPACE_TOOLCHAIN_CONFIG
}

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $WorkspaceRoot "validation\config\toolchain.local.json"
}

if (-not (Test-Path -LiteralPath $sourceDir)) {
    throw "missing source dir: $sourceDir"
}

if (-not (Test-Path -LiteralPath $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir | Out-Null
}

if (-not (Test-Path -LiteralPath $plcrexDir)) {
    New-Item -ItemType Directory -Path $plcrexDir | Out-Null
}

if (-not (Test-Path -LiteralPath $iecDir)) {
    New-Item -ItemType Directory -Path $iecDir | Out-Null
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "missing toolchain config: $ConfigPath"
}

$config = Get-Content -Raw $ConfigPath | ConvertFrom-Json
$py39 = $config.py39
$plcrexCliScript = $config.plcrex_cli_script
$iecCheckerExe = $config.iec_checker_exe
$sourceFiles = Get-ChildItem -LiteralPath $sourceDir -Filter "*.st" | Sort-Object Name

if (-not $sourceFiles) {
    throw "no .st source found in: $sourceDir"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$summaryFile = Join-Path $reportDir ("static-gate-" + $timestamp + ".md")
$parserRuns = @()
$iecRuns = @()
$parserExit = 0
$iecExit = 0

foreach ($sourceFile in $sourceFiles) {
    $parserExport = Join-Path $plcrexDir ("parser-" + $timestamp + "-" + [IO.Path]::GetFileNameWithoutExtension($sourceFile.Name))
    $parserArgs = @()
    if ($plcrexCliScript) {
        $parserArgs += @($plcrexCliScript, "st-parser")
    }
    else {
        $parserArgs += @("-m", "plcrex", "st-parser")
    }
    $parserArgs += @(('"' + $sourceFile.FullName + '"'), ('"' + $parserExport + '"'))

    $parserRun = Invoke-CapturedProcess -FilePath $py39 -Arguments $parserArgs
    $parserRuns += [pscustomobject]@{
        Source = $sourceFile.FullName
        Export = $parserExport
        ExitCode = $parserRun.ExitCode
        Output = $parserRun.Output
    }
    if ($parserRun.ExitCode -ne 0) {
        $parserExit = $parserRun.ExitCode
    }

    if (Test-Path -LiteralPath $iecCheckerExe) {
        $iecLog = Join-Path $iecDir ("iec-check-" + $timestamp + "-" + [IO.Path]::GetFileNameWithoutExtension($sourceFile.Name) + ".log")
        $iecArgs = @()
        if ($plcrexCliScript) {
            $iecArgs += @($plcrexCliScript, "iec-check")
        }
        else {
            $iecArgs += @("-m", "plcrex", "iec-check")
        }
        $iecArgs += @(('"' + $sourceFile.FullName + '"'), ('"' + $iecCheckerExe + '"'), ('"' + $iecLog + '"'))

        $iecRun = Invoke-CapturedProcess -FilePath $py39 -Arguments $iecArgs
        $iecRuns += [pscustomobject]@{
            Source = $sourceFile.FullName
            Log = $iecLog
            ExitCode = $iecRun.ExitCode
            Output = $iecRun.Output
        }
        if ($iecRun.ExitCode -ne 0) {
            $iecExit = $iecRun.ExitCode
        }
    }
}

$lines = @()
$lines += "# Static Gate"
$lines += ""
$lines += "- project: $ProjectPath"
$lines += "- checked_at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$lines += "- source_dir: $sourceDir"
$lines += "- source_count: $($sourceFiles.Count)"
$lines += ""
$lines += "## Commands"
$lines += ""
$lines += '- `plcrex st-parser`'
$lines += '- `plcrex iec-check`'
$lines += ""
$lines += "## Results"
$lines += ""
$lines += "- parser_exit: $parserExit"
if ($iecRuns.Count -gt 0) {
    $lines += "- iec_check_exit: $iecExit"
}
else {
    $lines += "- iec_check_exit: skipped"
    $lines += "- iec_log: missing iec-checker executable"
}
$lines += ""
foreach ($parserRun in $parserRuns) {
    $lines += "## Parser Output: $($parserRun.Source)"
    $lines += ""
    $lines += "- parser_export: $($parserRun.Export)"
    $lines += "- parser_file_exit: $($parserRun.ExitCode)"
    $lines += ""
    $lines += '```text'
    $lines += $parserRun.Output.Trim()
    $lines += '```'
    $lines += ""
}
foreach ($iecRun in $iecRuns) {
    $lines += "## IEC Checker Output: $($iecRun.Source)"
    $lines += ""
    $lines += "- iec_log: $($iecRun.Log)"
    $lines += "- iec_file_exit: $($iecRun.ExitCode)"
    $lines += ""
    $lines += '```text'
    $lines += $iecRun.Output.Trim()
    $lines += '```'
    $lines += ""
}

Set-Content -LiteralPath $summaryFile -Value ($lines -join "`r`n") -Encoding UTF8
Write-Output "Wrote: $summaryFile"
