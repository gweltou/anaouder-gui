@echo off
REM start.bat
REM Double-click this file to launch the app.

setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo It looks like the app hasn't been installed yet.
    echo Please double-click 'install.bat' first.
    echo.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo Starting Anaouder in terminal mode...
python .\main.py

if errorlevel 1 (
    echo.
    echo The app closed with an error.
    pause
)
