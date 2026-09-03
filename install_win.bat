@echo off
REM install.bat
REM Double-click this file to set up the app. Safe to run more than once.

setlocal

REM Always work from the folder this script lives in
cd /d "%~dp0"

echo ==============================================
echo  Installing the app - please wait...
echo ==============================================

REM 1. Find a Python launcher (py preferred, fallback to python)
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo.
        echo ERROR: Python was not found on this PC.
        echo Please install it from https://www.python.org/downloads/
        echo IMPORTANT: during installation, check the box "Add python.exe to PATH".
        echo Then run this script again.
        echo.
        pause
        exit /b 1
    )
)

echo Found Python launcher: %PYTHON%

REM 2. Create the virtual environment if it doesn't already exist
if not exist ".venv" (
    echo Creating virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: Could not create the virtual environment.
        echo.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists, reusing it.
)

REM 3. Activate it and install dependencies
call ".venv\Scripts\activate.bat"

echo Upgrading pip...
python -m pip install --upgrade pip --quiet

if exist "pyproject.toml" (
    echo Installing app and dependencies from pyproject.toml...
    python -m pip install .
    if errorlevel 1 (
        echo.
        echo ERROR: Installation from pyproject.toml failed ^(see messages above^).
        echo.
        pause
        exit /b 1
    )
) else if exist "requirements.txt" (
    echo Installing dependencies from requirements.txt...
    python -m pip install -r requirements.txt
) else (
    echo No pyproject.toml or requirements.txt found - installing PySide6 directly...
    python -m pip install PySide6
)

echo.
echo ==============================================
echo  Installation complete!
echo  You can now double-click 'start.bat' to launch the app.
echo ==============================================
echo.
pause
