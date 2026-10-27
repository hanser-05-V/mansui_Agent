param([switch]$DownloadOnly)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\environment.ps1"
$root = 'E:\QQAgent'
if ((Get-Item -LiteralPath $root).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse root refused' }
$dirs = @('runtime\downloads','runtime\tmp','runtime\test-state','runtime\state','runtime\tools\uv','config','logs')
foreach ($dir in $dirs) { [IO.Directory]::CreateDirectory((Join-Path $root $dir)) | Out-Null }
Add-Type -AssemblyName System.IO.Compression.FileSystem
function Expand-CheckedZip([string]$archive,[string]$destination,[string]$stripPrefix='') {
    $base = [IO.Path]::GetFullPath($destination).TrimEnd('\') + '\'
    if (-not $base.StartsWith('E:\QQAgent\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Extraction outside project' }
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('/','\')
            if ($stripPrefix) {
                if (-not $name.StartsWith($stripPrefix,[StringComparison]::Ordinal)) { throw 'Unexpected archive prefix' }
                $name = $name.Substring($stripPrefix.Length)
            }
            if (-not $name) { continue }
            if ([IO.Path]::IsPathRooted($name) -or $name.Contains(':') -or (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'Unsafe archive member' }
            $target = [IO.Path]::GetFullPath((Join-Path $base $name))
            if (-not $target.StartsWith($base,[StringComparison]::OrdinalIgnoreCase)) { throw 'Archive traversal refused' }
        }
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('/','\')
            if ($stripPrefix) { $name = $name.Substring($stripPrefix.Length) }
            if (-not $name) { continue }
            $target = [IO.Path]::GetFullPath((Join-Path $base $name))
            if ($name.EndsWith('\')) { [IO.Directory]::CreateDirectory($target) | Out-Null; continue }
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
            if (Test-Path -LiteralPath $target) { continue }
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target,$false)
        }
    } finally { $zip.Dispose() }
}
$assets = @(
 @{name='astrbot';version='v4.29.3';url='https://github.com/AstrBotDevs/AstrBot/archive/refs/tags/v4.29.3.zip';file='AstrBot-v4.29.3.zip';hash='';dest='app\AstrBot';prefix='AstrBot-4.29.3\'},
 @{name='dashboard';version='v4.29.3';url='https://github.com/AstrBotDevs/AstrBot/releases/download/v4.29.3/AstrBot-v4.29.3-dashboard.zip';file='AstrBot-dashboard-v4.29.3.zip';hash='a09f560c4140b930180f63a4929c885da80e24fb9bbda56619727bd25e985a11';dest='app\AstrBot\dashboard-release';prefix=''},
 @{name='napcat';version='v4.18.41';url='https://github.com/NapNeko/NapCatQQ/releases/download/v4.18.41/NapCat.Shell.zip';file='NapCat-Shell-v4.18.41.zip';hash='6801f93e533846cea05f4f531874a0e84371ab2331c5585b57cd7e3b869cf96b';dest='app\NapCat';prefix=''},
 @{name='uv';version='0.13.6';url='https://github.com/astral-sh/uv/releases/download/0.13.6/uv-x86_64-pc-windows-msvc.zip';file='uv-0.13.6.zip';hash='a2a8820d5eea32f08ef467ef3b7f66883a9b076d5737a2fc2fbb5f458d1bb50f';dest='runtime\tools\uv';prefix=''}
)
$records = @()
foreach ($asset in $assets) {
    $path = Join-Path "$root\runtime\downloads" $asset.file
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Output "Downloading $($asset.name) $($asset.version)"
        Invoke-WebRequest -Uri $asset.url -OutFile "$path.partial" -TimeoutSec 180
        if (Test-Path -LiteralPath $path) { throw 'Unexpected existing download' }
        Move-Item -LiteralPath "$path.partial" -Destination $path
    }
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
    if ($asset.hash -and $asset.hash -ne $hash) { throw "Digest mismatch: $($asset.name)" }
    Expand-CheckedZip $path (Join-Path $root $asset.dest) $asset.prefix
    $records += @{name=$asset.name;version=$asset.version;url=$asset.url;sha256=$hash;release_digest_verified=[bool]$asset.hash}
}
$previousLock = $null
if (Test-Path -LiteralPath "$root\config\versions.lock.json") { $previousLock = Get-Content -LiteralPath "$root\config\versions.lock.json" -Raw | ConvertFrom-Json }
$lock = @{created_utc=[DateTime]::UtcNow.ToString('o');assets=$records;python='3.12.16';dependency_lock_origin='locally_resolved_from_release_pyproject'}
if ($previousLock -and $previousLock.qq_launch) { $lock.qq_launch = $previousLock.qq_launch }
if (-not $DownloadOnly) {
    & "$root\runtime\tools\uv\uv.exe" python install 3.12.16
    if ($LASTEXITCODE -ne 0) { throw 'private_python_install_failed' }
    if (-not (Test-Path -LiteralPath "$root\app\AstrBot\uv.lock")) {
        & "$root\runtime\tools\uv\uv.exe" lock --project "$root\app\AstrBot" --python 3.12.16
        if ($LASTEXITCODE -ne 0) { throw 'dependency_lock_failed' }
    }
    & "$root\runtime\tools\uv\uv.exe" sync --frozen --no-install-project --project "$root\app\AstrBot" --python 3.12.16 --group dev
    if ($LASTEXITCODE -ne 0) { throw 'locked_dependency_install_failed' }
    & "$root\runtime\tools\uv\uv.exe" pip check --python "$root\runtime\venv\Scripts\python.exe"
    if ($LASTEXITCODE -ne 0) { throw 'dependency_check_failed' }
}
if (Test-Path -LiteralPath "$root\app\AstrBot\uv.lock") {
    $lock.astrbot_lock_sha256=(Get-FileHash -LiteralPath "$root\app\AstrBot\uv.lock" -Algorithm SHA256).Hash.ToLower()
}
if (Test-Path -LiteralPath "$root\runtime\venv\Scripts\python.exe") {
    $manifest = & "$root\runtime\venv\Scripts\python.exe" -B -c 'import json,platform,importlib.metadata as m; print(json.dumps({"python":platform.python_version(),"packages":sorted([{ "name":d.metadata["Name"],"version":d.version} for d in m.distributions()],key=lambda x:x["name"].lower())}))'
    if ($LASTEXITCODE -ne 0) { throw 'dependency_manifest_failed' }
    $lock.runtime = $manifest | ConvertFrom-Json
}
$pluginSource = "$root\plugins\mansui_companion"
$pluginDest = "$root\data\astrbot\data\plugins\mansui_companion"
[IO.Directory]::CreateDirectory($pluginDest) | Out-Null
$pluginHashes = @{}
foreach ($file in Get-ChildItem -LiteralPath $pluginSource -File) {
    $target = Join-Path $pluginDest $file.Name
    if ((Test-Path -LiteralPath $target) -and ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Reparse plugin file refused' }
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    $sourceHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    if ($sourceHash -ne (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash) { throw 'Plugin copy checksum failed' }
    $pluginHashes[$file.Name] = $sourceHash.ToLower()
}
$lock.plugin_hashes = $pluginHashes
[IO.File]::WriteAllText("$root\config\versions.lock.json",($lock|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
Write-Output 'Preparation finished. QQ was not started.'
