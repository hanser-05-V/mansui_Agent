$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\environment.ps1"
$root = 'E:\QQAgent'
$python = "$root\runtime\venv\Scripts\python.exe"
$mutex = [Threading.Mutex]::new($false,'Local\QQAgentStart-25ed85e')
$owned = $false
try {
    $owned = $mutex.WaitOne(0)
    if (-not $owned) { Write-Output 'Startup is already in progress.'; exit 0 }
    & $python -B "$PSScriptRoot\status.py" --check
    if ($LASTEXITCODE -eq 0) { & $python -B "$PSScriptRoot\status.py"; exit 0 }
    & $python -B "$PSScriptRoot\preflight.py"
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed. See README and docs/operations.md.' }
    $process = Start-Process -FilePath $python -ArgumentList @('-B',('"' + "$PSScriptRoot\boot_astrbot.py" + '"')) -WorkingDirectory $root -WindowStyle Hidden -PassThru
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        if ($process.HasExited) { throw 'Startup failed. Check runtime/state/last_error.json.' }
        if (Test-Path -LiteralPath "$root\runtime\state\process.json") {
            & $python -B "$PSScriptRoot\status.py" --ready
            if ($LASTEXITCODE -eq 0) { break }
        }
    }
    Write-Output 'Keep Windows awake and connected. Use the status shortcut to inspect readiness.'
} catch { Write-Output $_.Exception.Message; exit 1 }
finally { if ($owned) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
