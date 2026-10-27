$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\environment.ps1"
& 'E:\QQAgent\runtime\venv\Scripts\python.exe' -B "$PSScriptRoot\status.py" --stop
exit $LASTEXITCODE
