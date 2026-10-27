@echo off
setlocal
"%~dp0runtime\venv\Scripts\python.exe" -B "%~dp0scripts\configure.py"
pause
endlocal
