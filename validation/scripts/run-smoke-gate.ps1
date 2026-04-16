param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,

    [string]$WorkspaceRoot = "E:\web\plc-workspace",

    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"

[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }

function Invoke-CapturedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = "",
        [int]$TimeoutSeconds = 600
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

function Get-FreeTcpPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    $listener.Stop()
    return $port
}

function Invoke-CurlJson {
    param(
        [string[]]$CurlArgs
    )

    $curlCommand = if (Get-Command curl.exe -ErrorAction SilentlyContinue) { "curl.exe" } else { "curl" }
    $output = & $curlCommand @CurlArgs 2>&1
    return [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output = (($output | Out-String).Trim())
    }
}

function Invoke-JsonApi {
    param(
        [string]$Method,
        [string]$Uri,
        [hashtable]$Headers = @{},
        [object]$Body = $null
    )

    try {
        if ($null -ne $Body) {
            $jsonBody = $Body | ConvertTo-Json -Compress
            $response = Invoke-RestMethod -Method $Method -Uri $Uri -Headers $Headers -ContentType "application/json" -Body $jsonBody -SkipCertificateCheck
        }
        else {
            $response = Invoke-RestMethod -Method $Method -Uri $Uri -Headers $Headers -SkipCertificateCheck
        }

        $output = if ($response -is [string]) {
            $response
        }
        else {
            $response | ConvertTo-Json -Compress -Depth 20
        }

        return [pscustomobject]@{
            ExitCode = 0
            Output = $output
        }
    }
    catch {
        $message = $_.Exception.Message
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            $message = $_.ErrorDetails.Message
        }
        return [pscustomobject]@{
            ExitCode = 1
            Output = $message
        }
    }
}

function Invoke-FileUploadApi {
    param(
        [string]$Uri,
        [hashtable]$Headers = @{},
        [string]$FilePath
    )

    $curlArgs = @("-k", "-sS", "-X", "POST")
    foreach ($key in $Headers.Keys) {
        $curlArgs += @("-H", ("{0}: {1}" -f $key, $Headers[$key]))
    }
    $curlArgs += @("-F", ("file=@{0}" -f $FilePath), $Uri)
    return Invoke-CurlJson -CurlArgs $curlArgs
}

function Invoke-OpenPLCSmokeFlow {
    param(
        [string]$HttpHost,
        [int]$HttpPort,
        [string]$HttpsHost,
        [int]$HttpsPort,
        [string]$ModbusHost,
        [int]$ModbusPort,
        [string]$ProjectOpenplcSourcePath,
        [string]$TestVectorsDir,
        [string]$ValidationPython,
        [string]$BehaviorProbeScript
    )

    $result = [ordered]@{
        HttpProbe = $null
        HttpReady = $false
        ApiCreateUser = $null
        ApiLogin = $null
        ApiLoginReady = $false
        ApiStatus = $null
        ApiStatusReady = $false
        ApiUpload = $null
        ApiCompilation = $null
        ApiCompilationReady = $false
        ApiStart = $null
        ApiStartReady = $false
        BehaviorProbe = $null
        BehaviorProbeReady = $false
        BehaviorProbePass = $false
        RuntimeLogs = $null
        SmokeStatus = @()
    }

    $httpRoot = "http://{0}:{1}/" -f $HttpHost, $HttpPort
    $httpsRoot = "https://{0}:{1}" -f $HttpsHost, $HttpsPort
    $apiToken = ""

    for ($i = 0; $i -lt 24; $i++) {
        Start-Sleep -Seconds 5
        $result.HttpProbe = Invoke-CurlJson -CurlArgs @("-sS", $httpRoot)
        if ($result.HttpProbe.ExitCode -eq 0 -and $result.HttpProbe.Output) {
            $result.HttpReady = $true
            break
        }
    }

    if (-not $result.HttpReady) {
        $result.SmokeStatus += "HTTP dashboard probe failed"
        return [pscustomobject]$result
    }

    $result.SmokeStatus += "HTTP dashboard responded"
    $result.ApiCreateUser = Invoke-JsonApi -Method "Post" -Uri ($httpsRoot + "/api/create-user") -Body @{
        username = "smoke"
        password = "smoke-pass"
        role = "user"
    }

    $result.ApiLogin = Invoke-JsonApi -Method "Post" -Uri ($httpsRoot + "/api/login") -Body @{
        username = "smoke"
        password = "smoke-pass"
    }

    if ($result.ApiLogin.ExitCode -eq 0 -and $result.ApiLogin.Output) {
        try {
            $apiLoginJson = $result.ApiLogin.Output | ConvertFrom-Json
            $apiToken = $apiLoginJson.access_token
            if ($apiToken) {
                $result.ApiLoginReady = $true
                $result.SmokeStatus += "API login succeeded"
                Start-Sleep -Seconds 2
            }
        }
        catch {
        }
    }

    if (-not $result.ApiLoginReady) {
        return [pscustomobject]$result
    }

    $apiHeaders = @{ Authorization = ("Bearer {0}" -f $apiToken) }
    $result.ApiStatus = Invoke-CurlJson -CurlArgs @(
        "-k",
        "-sS",
        "-H", ("Authorization: Bearer {0}" -f $apiToken),
        ($httpsRoot + "/api/status")
    )
    if ($result.ApiStatus.ExitCode -eq 0 -and $result.ApiStatus.Output) {
        $result.ApiStatusReady = $true
        $result.SmokeStatus += "API status probe succeeded"
    }

    if ($ProjectOpenplcSourcePath) {
        $result.ApiUpload = Invoke-FileUploadApi -Uri ($httpsRoot + "/api/upload-file") -Headers $apiHeaders -FilePath $ProjectOpenplcSourcePath

        for ($i = 0; $i -lt 24; $i++) {
            Start-Sleep -Seconds 5
            $result.ApiCompilation = Invoke-CurlJson -CurlArgs @(
                "-k",
                "-sS",
                "-H", ("Authorization: Bearer {0}" -f $apiToken),
                ($httpsRoot + "/api/compilation-status")
            )
            if ($result.ApiCompilation.ExitCode -eq 0 -and $result.ApiCompilation.Output -match '"status"\s*:\s*"SUCCESS"|\"status\":\s*\"FAILED\"') {
                $result.ApiCompilationReady = $true
                break
            }
        }

        if ($result.ApiCompilationReady) {
            $result.SmokeStatus += "Project OpenPLC upload/compilation probe completed"

            if ($result.ApiCompilation.Output -match '"status"\s*:\s*"SUCCESS"') {
                $result.ApiStart = Invoke-CurlJson -CurlArgs @(
                    "-k",
                    "-sS",
                    "-H", ("Authorization: Bearer {0}" -f $apiToken),
                    ($httpsRoot + "/api/start-plc")
                )

                if ($result.ApiStart.ExitCode -eq 0 -and $result.ApiStart.Output) {
                    for ($i = 0; $i -lt 24; $i++) {
                        Start-Sleep -Seconds 2
                        $result.ApiStatus = Invoke-CurlJson -CurlArgs @(
                            "-k",
                            "-sS",
                            "-H", ("Authorization: Bearer {0}" -f $apiToken),
                            ($httpsRoot + "/api/status")
                        )
                        if ($result.ApiStatus.ExitCode -eq 0 -and $result.ApiStatus.Output -match 'STATUS:RUNNING') {
                            $result.ApiStartReady = $true
                            $result.SmokeStatus += "PLC runtime entered RUNNING"
                            break
                        }
                    }
                }

                if ($result.ApiStartReady) {
                    if ((Test-Path -LiteralPath $ValidationPython) -and (Test-Path -LiteralPath $BehaviorProbeScript)) {
                        $result.BehaviorProbe = Invoke-CapturedProcess -FilePath $ValidationPython -Arguments @(
                            $BehaviorProbeScript,
                            "--host", $ModbusHost,
                            "--port", $ModbusPort,
                            "--timeout-seconds", "20",
                            "--poll-interval", "0.5",
                            "--vectors-dir", $TestVectorsDir
                        ) -TimeoutSeconds 60
                        $result.BehaviorProbeReady = $result.BehaviorProbe.ExitCode -ge 0
                        $result.BehaviorProbePass = $result.BehaviorProbe.ExitCode -eq 0

                        if ($result.BehaviorProbePass) {
                            $result.SmokeStatus += "Behavior probe passed"
                        }
                        else {
                            $result.SmokeStatus += "Behavior probe failed"
                        }
                    }
                    else {
                        $result.SmokeStatus += "Behavior probe prerequisites missing"
                    }
                }
                else {
                    $result.SmokeStatus += "PLC runtime failed to enter RUNNING"
                }
            }
        }
    }

    $result.RuntimeLogs = Invoke-CurlJson -CurlArgs @(
        "-k",
        "-sS",
        "-H", ("Authorization: Bearer {0}" -f $apiToken),
        ($httpsRoot + "/api/runtime-logs")
    )

    return [pscustomobject]$result
}

$reportDir = Join-Path $ProjectPath "04_reports\smoke"

if (-not $ConfigPath) {
    $ConfigPath = $env:PLC_WORKSPACE_TOOLCHAIN_CONFIG
}

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $WorkspaceRoot "validation\config\toolchain.local.json"
}

if (-not (Test-Path -LiteralPath $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir | Out-Null
}

$config = Get-Content -Raw $ConfigPath | ConvertFrom-Json
$openplcMode = $config.openplc_mode
$openplcRepoDir = $config.openplc_repo_dir
$openplcImageTag = $config.openplc_image_tag
$openplcDockerfile = $config.openplc_smoke_dockerfile
if (-not $openplcMode) {
    $openplcMode = "docker"
}
if (-not $openplcImageTag) {
    $openplcImageTag = "plc-workspace-openplc:v3-smoke"
}
if (-not $openplcDockerfile) {
    $openplcDockerfile = Join-Path $WorkspaceRoot "validation\docker\OpenPLC.smoke.Dockerfile"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$summaryFile = Join-Path $reportDir ("smoke-gate-" + $timestamp + ".md")
$projectOpenplcDir = Join-Path $ProjectPath "03_checks\openplc"
$projectOpenplcSource = Get-ChildItem -LiteralPath $projectOpenplcDir -Filter "*.st" -ErrorAction SilentlyContinue | Select-Object -First 1
$testVectorsDir = Join-Path $ProjectPath "03_checks\test_vectors"
$testVectorFiles = @()
if (Test-Path -LiteralPath $testVectorsDir) {
    $testVectorFiles = Get-ChildItem -LiteralPath $testVectorsDir -Filter "*.yaml" | Sort-Object Name
}
$dockerCommand = if (Get-Command docker.exe -ErrorAction SilentlyContinue) { "docker.exe" } else { "docker" }
$dockerInfo = [pscustomobject]@{
    ExitCode = 0
    Output = "docker skipped: external OpenPLC runtime mode"
}
$dockerReady = $true
if ($openplcMode -ne "external") {
    $dockerInfo = Invoke-CapturedProcess -FilePath $dockerCommand -Arguments @("info") -TimeoutSeconds 60
    $dockerReady = $dockerInfo.ExitCode -eq 0 -and $dockerInfo.Output -match "Server:"
}
$dockerImageInspect = $null
$dockerBuild = $null
$dockerBuildReady = $false
$containerName = "plc-smoke-" + $timestamp.ToLower()
$httpHost = if ($config.openplc_http_host) { [string]$config.openplc_http_host } else { "127.0.0.1" }
$httpsHost = if ($config.openplc_https_host) { [string]$config.openplc_https_host } else { $httpHost }
$modbusHost = if ($config.openplc_modbus_host) { [string]$config.openplc_modbus_host } else { $httpHost }
$httpPort = if ($openplcMode -eq "external" -and $config.openplc_http_port) { [int]$config.openplc_http_port } else { Get-FreeTcpPort }
$httpsPort = if ($openplcMode -eq "external" -and $config.openplc_https_port) { [int]$config.openplc_https_port } else { Get-FreeTcpPort }
$modbusPort = if ($openplcMode -eq "external" -and $config.openplc_modbus_port) { [int]$config.openplc_modbus_port } else { Get-FreeTcpPort }
$dockerRun = $null
$containerStarted = $false
$httpProbe = $null
$httpReady = $false
$apiLogin = $null
$apiToken = ""
$apiCreateUser = $null
$apiLoginReady = $false
$apiStatus = $null
$apiStatusReady = $false
$apiUpload = $null
$apiCompilation = $null
$apiCompilationReady = $false
$apiStart = $null
$apiStartReady = $false
$behaviorProbe = $null
$behaviorProbeReady = $false
$behaviorProbePass = $false
$runtimeLogs = $null
$smokeStatus = @()
$validationPython = if ($config.py39) { $config.py39 } else { Join-Path $WorkspaceRoot "validation\.venv39\Scripts\python.exe" }
$behaviorProbeScript = Join-Path $WorkspaceRoot "validation\scripts\openplc_behavior_probe.py"
$flowResult = $null

if ($openplcMode -eq "external") {
    $dockerBuildReady = $true
    $containerStarted = $true
    $smokeStatus += "OpenPLC external runtime selected"
    $flowResult = Invoke-OpenPLCSmokeFlow `
        -HttpHost $httpHost `
        -HttpPort $httpPort `
        -HttpsHost $httpsHost `
        -HttpsPort $httpsPort `
        -ModbusHost $modbusHost `
        -ModbusPort $modbusPort `
        -ProjectOpenplcSourcePath $projectOpenplcSource.FullName `
        -TestVectorsDir $testVectorsDir `
        -ValidationPython $validationPython `
        -BehaviorProbeScript $behaviorProbeScript
}
elseif ($dockerReady -and $openplcRepoDir -and (Test-Path -LiteralPath $openplcRepoDir)) {
    $baseImage = "debian:trixie-20251020"
    $baseImageInspect = Invoke-CapturedProcess -FilePath $dockerCommand -Arguments @("image", "inspect", $baseImage) -TimeoutSeconds 60
    if ($baseImageInspect.ExitCode -ne 0) {
        $baseImagePull = Invoke-CapturedProcess -FilePath $dockerCommand -Arguments @("pull", $baseImage) -TimeoutSeconds 1800
        if ($baseImagePull.ExitCode -ne 0) {
            $smokeStatus += "OpenPLC base image pull failed"
        }
    }

    $dockerImageInspect = Invoke-CapturedProcess -FilePath $dockerCommand -Arguments @("image", "inspect", $openplcImageTag) -TimeoutSeconds 60
    if ($dockerImageInspect.ExitCode -eq 0) {
        $dockerBuildReady = $true
        $smokeStatus += "OpenPLC image already available"
    }
    else {
        $dockerBuild = Invoke-CapturedProcess -FilePath $dockerCommand -WorkingDirectory $openplcRepoDir -TimeoutSeconds 1800 -Arguments @(
            "build",
            "--pull=false",
            "-f", $openplcDockerfile,
            "--build-arg", "HTTP_PROXY=",
            "--build-arg", "HTTPS_PROXY=",
            "--build-arg", "ALL_PROXY=",
            "--build-arg", "http_proxy=",
            "--build-arg", "https_proxy=",
            "--build-arg", "all_proxy=",
            "-t", $openplcImageTag,
            "."
        )
        $dockerBuildReady = $dockerBuild.ExitCode -eq 0
        if ($dockerBuildReady) {
            $smokeStatus += "OpenPLC image build succeeded"
        }
        else {
            $smokeStatus += "OpenPLC image build failed"
        }
    }

    if ($dockerBuildReady) {
        try {
            $dockerRun = Invoke-CapturedProcess -FilePath $dockerCommand -Arguments @(
                "run",
                "-d",
                "--rm",
                "--name", $containerName,
                "-e", "HTTP_PROXY=",
                "-e", "HTTPS_PROXY=",
                "-e", "ALL_PROXY=",
                "-e", "http_proxy=",
                "-e", "https_proxy=",
                "-e", "all_proxy=",
                "-p", ("127.0.0.1:{0}:8080" -f $httpPort),
                "-p", ("127.0.0.1:{0}:8443" -f $httpsPort),
                "-p", ("127.0.0.1:{0}:502" -f $modbusPort),
                $openplcImageTag
            ) -TimeoutSeconds 120
            $containerStarted = $dockerRun.ExitCode -eq 0

            if ($containerStarted) {
                $smokeStatus += "OpenPLC container started"
                $flowResult = Invoke-OpenPLCSmokeFlow `
                    -HttpHost $httpHost `
                    -HttpPort $httpPort `
                    -HttpsHost $httpsHost `
                    -HttpsPort $httpsPort `
                    -ModbusHost $modbusHost `
                    -ModbusPort $modbusPort `
                    -ProjectOpenplcSourcePath $projectOpenplcSource.FullName `
                    -TestVectorsDir $testVectorsDir `
                    -ValidationPython $validationPython `
                    -BehaviorProbeScript $behaviorProbeScript
            }
            else {
                $smokeStatus += "OpenPLC container failed to start"
            }
        }
        finally {
            Invoke-CapturedProcess -FilePath $dockerCommand -Arguments @("rm", "-f", $containerName) -TimeoutSeconds 60 | Out-Null
        }
    }
}
elseif (-not $dockerReady) {
    $smokeStatus += "Docker daemon not ready"
}
elseif (-not $openplcRepoDir) {
    $smokeStatus += "OpenPLC repo dir not configured"
}
else {
    $smokeStatus += "OpenPLC repo dir missing on disk"
}

if ($flowResult) {
    $httpProbe = $flowResult.HttpProbe
    $httpReady = $flowResult.HttpReady
    $apiCreateUser = $flowResult.ApiCreateUser
    $apiLogin = $flowResult.ApiLogin
    $apiLoginReady = $flowResult.ApiLoginReady
    $apiStatus = $flowResult.ApiStatus
    $apiStatusReady = $flowResult.ApiStatusReady
    $apiUpload = $flowResult.ApiUpload
    $apiCompilation = $flowResult.ApiCompilation
    $apiCompilationReady = $flowResult.ApiCompilationReady
    $apiStart = $flowResult.ApiStart
    $apiStartReady = $flowResult.ApiStartReady
    $behaviorProbe = $flowResult.BehaviorProbe
    $behaviorProbeReady = $flowResult.BehaviorProbeReady
    $behaviorProbePass = $flowResult.BehaviorProbePass
    $runtimeLogs = $flowResult.RuntimeLogs
    $smokeStatus += $flowResult.SmokeStatus
}

$lines = @()
$lines += "# Smoke Gate"
$lines += ""
$lines += "- project: $ProjectPath"
$lines += "- checked_at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$lines += "- openplc_repo_dir: $openplcRepoDir"
$lines += "- openplc_image_tag: $openplcImageTag"
$lines += "- openplc_dockerfile: $openplcDockerfile"
$lines += "- openplc_mode: $openplcMode"
$lines += "- openplc_http_host: $httpHost"
$lines += "- openplc_https_host: $httpsHost"
$lines += "- openplc_modbus_host: $modbusHost"
$lines += "- project_openplc_source: $($projectOpenplcSource.FullName)"
$lines += "- test_vectors_dir: $testVectorsDir"
$lines += "- test_vector_count: $($testVectorFiles.Count)"
$lines += ""
$lines += "## Expected checks"
$lines += ""
$lines += "- OpenPLC_v3 runtime smoke"
$lines += "- one full run"
$lines += "- reset replay"
$lines += "- deadlock / obvious timer issues"
$lines += "- criteria loaded from test_vectors/*.yaml"
$lines += ""
if ($testVectorFiles.Count -gt 0) {
    $lines += "## Test Vectors"
    $lines += ""
    foreach ($vectorFile in $testVectorFiles) {
        $lines += "- $($vectorFile.Name)"
    }
    $lines += ""
}
$lines += ""
$lines += "## Current status"
$lines += ""
$lines += "- docker_ready: $dockerReady"
$lines += "- docker_build_ready: $dockerBuildReady"
$lines += "- container_started: $containerStarted"
$lines += "- http_ready: $httpReady"
$lines += "- api_login_ready: $apiLoginReady"
$lines += "- api_status_ready: $apiStatusReady"
$lines += "- api_compilation_ready: $apiCompilationReady"
$lines += "- api_start_ready: $apiStartReady"
$lines += "- behavior_probe_ready: $behaviorProbeReady"
$lines += "- behavior_probe_pass: $behaviorProbePass"
$lines += "- http_port: $httpPort"
$lines += "- https_port: $httpsPort"
$lines += "- modbus_port: $modbusPort"
$lines += ""
$lines += "## Smoke Status"
$lines += ""
foreach ($statusLine in $smokeStatus) {
    $lines += "- $statusLine"
}
$lines += ""
$lines += "## Docker Info"
$lines += ""
$lines += '```text'
$lines += $dockerInfo.Output.Trim()
$lines += '```'
if ($dockerBuild) {
    $lines += ""
    $lines += "## Docker Build Output"
    $lines += ""
    $lines += '```text'
    $lines += $dockerBuild.Output.Trim()
    $lines += '```'
}
if ($dockerRun) {
    $lines += ""
    $lines += "## Docker Run Output"
    $lines += ""
    $lines += '```text'
    $lines += $dockerRun.Output.Trim()
    $lines += '```'
}
if ($httpProbe) {
    $lines += ""
    $lines += "## HTTP Probe"
    $lines += ""
    $lines += '```text'
    $lines += $httpProbe.Output.Trim()
    $lines += '```'
}
if ($apiCreateUser) {
    $lines += ""
    $lines += "## API Create User"
    $lines += ""
    $lines += '```text'
    $lines += $apiCreateUser.Output.Trim()
    $lines += '```'
}
if ($apiLogin) {
    $lines += ""
    $lines += "## API Login"
    $lines += ""
    $lines += '```text'
    $lines += $apiLogin.Output.Trim()
    $lines += '```'
}
if ($apiStatus) {
    $lines += ""
    $lines += "## API Status"
    $lines += ""
    $lines += '```text'
    $lines += $apiStatus.Output.Trim()
    $lines += '```'
}
if ($apiUpload) {
    $lines += ""
    $lines += "## API Upload"
    $lines += ""
    $lines += '```text'
    $lines += $apiUpload.Output.Trim()
    $lines += '```'
}
if ($apiCompilation) {
    $lines += ""
    $lines += "## API Compilation Status"
    $lines += ""
    $lines += '```text'
    $lines += $apiCompilation.Output.Trim()
    $lines += '```'
}
if ($apiStart) {
    $lines += ""
    $lines += "## API Start PLC"
    $lines += ""
    $lines += '```text'
    $lines += $apiStart.Output.Trim()
    $lines += '```'
}
if ($behaviorProbe) {
    $lines += ""
    $lines += "## Behavior Probe"
    $lines += ""
    $lines += '```text'
    $lines += $behaviorProbe.Output.Trim()
    $lines += '```'
}
if ($runtimeLogs) {
    $lines += ""
    $lines += "## Runtime Logs"
    $lines += ""
    $lines += '```text'
    $lines += $runtimeLogs.Output.Trim()
    $lines += '```'
}

Set-Content -LiteralPath $summaryFile -Value ($lines -join "`r`n") -Encoding UTF8
Write-Output "Wrote: $summaryFile"
