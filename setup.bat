@echo off
setlocal EnableDelayedExpansion

:: This script prepares the Python environment for the DEM processing scripts.

:: Setup Python 3.10 if needed, it will be used in the virtual environment.
:: Step 1: Check if Python 3.10 is installed using the py launcher
py -3.10 --version >nul 2>&1

:: Check the result of the command
if %ERRORLEVEL% EQU 0 (
    echo Python 3.10 found. Proceeding...
) else (
    echo Python 3.10 not found. Installing Python 3.10 locally...

    :: Step 2: Select bundled Python 3.10 installer
    set INSTALLER=install/python-3.10.11-amd64.exe

    :: Step 3: Install Python 3.10 locally for the virtual environment (without modifying system Python)
    echo Installing Python 3.10...
    start /wait !INSTALLER! /quiet InstallAllUsers=0 PrependPath=0

    :: Clean up the installer after installation
    del !INSTALLER!

    :: Step 4: Find the Python 3.10 installation path (default is in the user's AppData)
    :: Modify this path based on where the Python 3.10 installer places Python locally
    set PYTHON_PATH=!LOCALAPPDATA!\Programs\Python\Python310\python.exe

    :: Verify the Python 3.10 installation by calling it directly
    if exist "!PYTHON_PATH!" (
        echo Python 3.10 installation found at !PYTHON_PATH!.
    ) else (
        echo Python 3.10 installation failed. Please install Python 3.10 manually.
        exit /b
    )
)

:: Set the path to the (pre-existing or newly installed) Python 3.10.
set PYTHON_PATH=!LOCALAPPDATA!\Programs\Python\Python310\python.exe
echo Started setup of DEM tools...

:: Create virtual environment if it doesn't exist
if not exist venv (
    echo Creating virtual environment...
    !PYTHON_PATH! -m venv venv
)

:: Activate virtual environment
call venv\Scripts\activate

:: Upgrade pip
echo Upgrading pip...
venv\Scripts\python.exe -m pip install --upgrade pip

:: Install dependencies
echo Installing dependencies from requirements.txt...
venv\Scripts\python.exe -m pip install -r requirements.txt

endlocal
pause
