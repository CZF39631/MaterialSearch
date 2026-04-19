@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "PYTHONW=%PROJECT_DIR%\.venv\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
    echo Pythonw not found: %PYTHONW%
    pause
    exit /b 1
)

start "MaterialSearch Tray" "%PYTHONW%" "%PROJECT_DIR%\tray_app.py"
exit /b 0
