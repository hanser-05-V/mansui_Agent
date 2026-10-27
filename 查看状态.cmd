@echo off
setlocal
"%~dp0runtime\venv\Scripts\python.exe" -B "%~dp0scripts\status.py"
pause
endlocal
