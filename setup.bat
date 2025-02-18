@echo off
setlocal

:: Check if Python is installed
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python is not installed or not added to PATH.
    echo Please install Python 3 and try again.
    exit /b 1
)

echo Started setup of DEM tools...

:: Create virtual environment if it doesn't exist
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

:: Activate virtual environment
call venv\Scripts\activate

:: Upgrade pip
echo Upgrading pip...
venv\Scripts\python.exe -m pip install --upgrade pip

:: Install dependencies
if exist requirements.txt (
    echo Installing dependencies from requirements.txt...
    venv\Scripts\python.exe -m pip install -r requirements.txt
) else (
    echo No requirements.txt found. Skipping package installation.
)

endlocal
pause
