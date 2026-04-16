param(
    [string]$Project = "FB_MainSequence",
    [string]$OutputPath = "",
    [switch]$AllProjects
)

$ErrorActionPreference = "Stop"

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BasePath,
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $baseUri = [System.Uri]((Resolve-Path -LiteralPath $BasePath).Path.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar)
    $pathUri = [System.Uri]((Resolve-Path -LiteralPath $Path).Path)
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace("/", [IO.Path]::DirectorySeparatorChar)
}

function Test-ExcludedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $p = $RelativePath.Replace("\", "/")

    if ($p -match '(^|/)\.git(/|$)') { return $true }
    if ($p -match '(^|/)\.claude(/|$)') { return $true }
    if ($p -match '(^|/)__pycache__(/|$)') { return $true }
    if ($p -match 'PLCreX_outputs') { return $true }
    if ($p -match '\.pyc$') { return $true }
    if ($p -match '\.log$') { return $true }
    if ($p -match '\.(zip|7z|rar|tar|tar\.gz)$') { return $true }

    if ($p -match '^workspace(/|$)') { return $true }
    if ($p -match '^以往项目(/|$)') { return $true }
    if ($p -match '^validation/\.venv39(/|$)') { return $true }
    if ($p -match '^validation/config/toolchain\.local\.json$') { return $true }

    if ($p -match '^projects/[^/]+/04_reports(/|$)') { return $true }
    if ($p -match '^projects/[^/]+/03_checks/plcrex/PLCreX_outputs(/|$)') { return $true }
    if ($p -match '^projects/[^/]+/03_checks/iec-checker/.*\.log$') { return $true }
    if ($p -match '^projects/[^/]+/03_checks/plcverif/output(/|$)') { return $true }
    if ($p -match '^projects/[^/]+/03_checks/plcverif/workspace(/|$)') { return $true }
    if ($p -match '^projects/[^/]+/03_checks/plcverif/plcverif\.log$') { return $true }

    if ($p -match '^validation/tools/plcverif/tools/workspace/[^/]+/output(/|$)') { return $true }
    if ($p -match '^validation/tools/plcverif/tools/workspace/[^/]+/workspace(/|$)') { return $true }
    if ($p -match '^validation/tools/plcverif/tools/workspace/[^/]+/plcverif\.log$') { return $true }

    return $false
}

function Copy-FilteredTree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceRoot,
        [Parameter(Mandatory = $true)]
        [string]$WorkspaceRoot,
        [Parameter(Mandatory = $true)]
        [string]$StagingRoot
    )

    if (-not (Test-Path -LiteralPath $SourceRoot)) {
        Write-Warning "Skipping missing runtime asset root: $SourceRoot"
        return 0
    }

    $copied = 0
    $files = Get-ChildItem -LiteralPath $SourceRoot -Recurse -File -Force
    foreach ($file in $files) {
        $relative = Get-RelativePath -BasePath $WorkspaceRoot -Path $file.FullName
        if (Test-ExcludedPath -RelativePath $relative) {
            continue
        }

        $dest = Join-Path $StagingRoot $relative
        $destDir = Split-Path -Parent $dest
        if (-not (Test-Path -LiteralPath $destDir)) {
            New-Item -ItemType Directory -Path $destDir | Out-Null
        }

        Copy-Item -LiteralPath $file.FullName -Destination $dest -Force
        $copied++
    }

    return $copied
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent $scriptDir
$releaseDir = Join-Path $workspaceRoot "releases"

if (-not $OutputPath) {
    $OutputPath = Join-Path $releaseDir "runtime-assets.zip"
}

if (-not (Test-Path -LiteralPath $releaseDir)) {
    New-Item -ItemType Directory -Path $releaseDir | Out-Null
}

$workspaceResolved = (Resolve-Path -LiteralPath $workspaceRoot).Path
$outputFullPath = [IO.Path]::GetFullPath($OutputPath)
$stagingRoot = Join-Path $releaseDir ".runtime-assets-staging"
$releaseResolved = [IO.Path]::GetFullPath($releaseDir)
$stagingFullPath = [IO.Path]::GetFullPath($stagingRoot)

if (-not $stagingFullPath.StartsWith($releaseResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "refusing to stage outside release dir: $stagingFullPath"
}

if (Test-Path -LiteralPath $stagingRoot) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $stagingRoot | Out-Null

$assetRoots = @(
    "docs/harness",
    "PLC素材库",
    "validation/tools/plcverif",
    "validation/tools/OpenPLC_v3",
    "validation/config",
    "validation/templates",
    "validation/docker"
)

if ($AllProjects) {
    $assetRoots += "projects"
}
else {
    $assetRoots += "projects/$Project"
}

$gitCommit = (& git -C $workspaceRoot rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0) {
    $gitCommit = "unknown"
}

$manifest = [ordered]@{
    created_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
    workspace_root = $workspaceResolved
    git_commit = $gitCommit
    project = if ($AllProjects) { "all" } else { $Project }
    included_roots = @()
    excluded_rules = @(
        ".git",
        ".claude",
        "workspace",
        "以往项目",
        "validation/.venv39",
        "validation/config/toolchain.local.json",
        "projects/*/04_reports",
        "*PLCreX_outputs*",
        "projects/*/03_checks/iec-checker/*.log",
        "projects/*/03_checks/plcverif/output",
        "projects/*/03_checks/plcverif/workspace",
        "projects/*/03_checks/plcverif/plcverif.log",
        "*.log",
        "*.zip",
        "__pycache__",
        "*.pyc"
    )
    file_count = 0
}

foreach ($root in $assetRoots) {
    $source = Join-Path $workspaceRoot $root
    $count = Copy-FilteredTree -SourceRoot $source -WorkspaceRoot $workspaceRoot -StagingRoot $stagingRoot
    if ($count -gt 0) {
        $manifest.included_roots += $root
        $manifest.file_count += $count
    }
}

$manifestPath = Join-Path $releaseDir "runtime-assets.manifest.json"
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $stagingRoot "runtime-assets.manifest.json") -Force

if (Test-Path -LiteralPath $outputFullPath) {
    Remove-Item -LiteralPath $outputFullPath -Force
}

$stagedItems = Join-Path $stagingRoot "*"
Compress-Archive -Path $stagedItems -DestinationPath $outputFullPath -CompressionLevel Optimal

Remove-Item -LiteralPath $stagingRoot -Recurse -Force

$zip = Get-Item -LiteralPath $outputFullPath
Write-Output "Wrote: $($zip.FullName)"
Write-Output "SizeMB: $([math]::Round($zip.Length / 1MB, 2))"
Write-Output "Manifest: $manifestPath"
Write-Output "Files: $($manifest.file_count)"
