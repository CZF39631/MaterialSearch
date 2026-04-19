@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python not found: %PYTHON%
    pause
    exit /b 1
)

pushd "%PROJECT_DIR%"

echo [1/3] Installing build dependencies...
"%PYTHON%" -m pip install pyinstaller pystray
if errorlevel 1 goto :fail

echo [2/3] Cleaning old build outputs...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Building tray executable...
"%PYTHON%" -m PyInstaller --clean tray_app.spec
if errorlevel 1 goto :fail

if not exist "dist\MaterialSearchTray\tmp" mkdir "dist\MaterialSearchTray\tmp"
copy /Y ".env.example" "dist\MaterialSearchTray\.env.example" >nul
copy /Y "TRAY_PACKING.md" "dist\MaterialSearchTray\TRAY_PACKING.md" >nul

echo.
echo Build finished: %PROJECT_DIR%dist\MaterialSearchTray\MaterialSearchTray.exe
echo Open the folder and run MaterialSearchTray.exe.
popd
exit /b 0

:fail
echo.
echo Build failed. Please check the log above.
popd
pause
exit /b 1
