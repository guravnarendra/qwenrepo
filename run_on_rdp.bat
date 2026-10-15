@echo off
setlocal enabledelayedexpansion
title Qwen-Image 2.1 Uncensored - Auto Setup & Launch
color 0B

echo =====================================================================
echo  🎨 Qwen-Image 2.1 Uncensored - Auto Installer & Runner for RDP
echo =====================================================================
echo.

:: =====================================================================
:: 1. GITHUB REPOSITORY CONFIGURATION
:: (Put your repository URL below if you want automatic cloning)
:: =====================================================================
set "REPO_URL=https://github.com/guravnarendra/qwenrepo.git"
set "CLONE_DIR=qwenrepo"

:: Check if run.py exists in the current directory or a subfolder
if not exist "run.py" (
    if exist "%CLONE_DIR%\run.py" (
        cd /d "%CLONE_DIR%"
    ) else (
        echo [INFO] run.py not found in the current folder.
        echo Checking Git to clone the repository from GitHub...
        echo.
    )
)

:: =====================================================================
:: 2. CHECK / INSTALL GIT
:: =====================================================================
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [1/6] Git is NOT installed. Attempting automatic installation...
    echo Downloading Git installer...
    curl.exe -L -o "%TEMP%\git_installer.exe" "https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to download Git. Please install Git manually from https://git-scm.com/
        pause
        exit /b 1
    )
    echo Installing Git silently...
    start /wait "" "%TEMP%\git_installer.exe" /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS
    del /f /q "%TEMP%\git_installer.exe" >nul 2>nul
    
    :: Add standard Git paths to current session
    set "PATH=C:\Program Files\Git\cmd;%LocalAppData%\Programs\Git\cmd;!PATH!"
    where git >nul 2>nul
    if %errorlevel% neq 0 (
        echo [WARNING] Git installed but not yet in PATH. Please restart this .bat file if cloning fails.
    ) else (
        echo [OK] Git successfully installed!
    )
) else (
    echo [OK] Git is already installed.
)
echo.

:: =====================================================================
:: 3. CLONE FROM GITHUB IF NOT ALREADY IN REPO FOLDER
:: =====================================================================
if not exist "run.py" (
    echo [2/6] GitHub Repository Setup...
    echo !REPO_URL! | findstr /I "YOUR_USERNAME" >nul
    if %errorlevel% equ 0 (
        echo.
        echo Please enter your GitHub repository URL to clone:
        set /p REPO_URL="Repo URL (e.g. https://github.com/user/fcc.git): "
    )
    
    if not "!REPO_URL!"=="" (
        echo Cloning repository from !REPO_URL!...
        git clone "!REPO_URL!" "%CLONE_DIR%"
        if exist "%CLONE_DIR%\run.py" (
            cd /d "%CLONE_DIR%"
            echo [OK] Cloned and switched into %CLONE_DIR%
        ) else (
            echo [ERROR] Failed to clone or run.py not found in repo!
            pause
            exit /b 1
        )
    ) else (
        echo [ERROR] No GitHub URL provided and run.py not found!
        pause
        exit /b 1
    )
) else (
    echo [OK] Project files verified.
    :: Pull latest changes if it is a git repo
    if exist ".git" (
        echo Checking for updates from GitHub...
        git pull --quiet
    )
)
echo.

:: =====================================================================
:: 4. CHECK / INSTALL PYTHON
:: =====================================================================
set "PYTHON_CMD="
where python >nul 2>nul
if %errorlevel% equ 0 (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>nul
    if %errorlevel% equ 0 (
        for /f "tokens=2 delims= " %%v in ('py --version 2^>^&1') do set "PY_VER=%%v"
        set "PYTHON_CMD=py"
    )
)

if "%PYTHON_CMD%"=="" (
    echo [3/6] Python is NOT installed. Installing Python 3.10.11 silently...
    echo Downloading official Python installer...
    curl.exe -L -o "%TEMP%\python_installer.exe" "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to download Python. Please install Python 3.10 manually from https://www.python.org/
        pause
        exit /b 1
    )
    echo Installing Python 3.10 (adding to PATH)...
    start /wait "" "%TEMP%\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 SimpleInstall=1
    del /f /q "%TEMP%\python_installer.exe" >nul 2>nul
    
    set "PATH=%LocalAppData%\Programs\Python\Python310;%LocalAppData%\Programs\Python\Python310\Scripts;!PATH!"
    set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python310\python.exe"
    if not exist "!PYTHON_CMD!" (
        set "PYTHON_CMD=python"
    )
    echo [OK] Python 3.10 installed successfully!
) else (
    echo [OK] Python detected: !PY_VER!
)
echo.

:: =====================================================================
:: 5. PYTHON VIRTUAL ENVIRONMENT (VENV) SETUP
:: =====================================================================
echo [4/6] Setting up Python Virtual Environment (venv)...
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment in .\venv...
    %PYTHON_CMD% -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat
echo [OK] Virtual environment activated: %VIRTUAL_ENV%
echo.

:: =====================================================================
:: 6. INSTALL DEPENDENCIES (PyTorch CUDA + Requirements)
:: =====================================================================
echo [5/6] Checking & Installing PyTorch CUDA and dependencies...

python -c "import torch; assert torch.cuda.is_available()" >nul 2>nul
if %errorlevel% neq 0 (
    echo Installing PyTorch with CUDA 12.4 support (this takes a few minutes)...
    python -m pip install --upgrade pip
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
    if %errorlevel% neq 0 (
        echo [WARNING] CUDA 12.4 installation had issues, trying CUDA 12.1...
        pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    )
) else (
    echo [OK] PyTorch with CUDA is already installed.
)

echo.
echo Installing required modules from requirements.txt...
pip install -r requirements.txt
pip install jupyterlab ipywidgets

echo.
echo [OK] All required modules installed successfully!
echo.

:: =====================================================================
:: 7. LAUNCH SELECTION
:: =====================================================================
echo =====================================================================
echo  Select how you want to run Qwen-Image 2.1:
echo  [1] Launch Gradio Web UI directly (Recommended - 1-Click Fast)
echo  [2] Launch Jupyter Notebook / Lab (to run the .ipynb file)
echo =====================================================================
echo.
set "CHOICE=1"
choice /c 12 /t 5 /d 1 /m "Auto-launching Web UI in 5 seconds (Press 1 or 2 to choose)"

if "%errorlevel%"=="2" (
    echo.
    echo 🚀 Starting Jupyter Lab...
    jupyter lab
) else (
    echo.
    echo 🚀 Starting Qwen-Image 2.1 Uncensored Web UI...
    python run.py
)

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] An error occurred while running the application.
    pause
)
