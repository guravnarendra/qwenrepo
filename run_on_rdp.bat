@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Qwen-Image 2.1 Uncensored - Auto Setup and Launch
color 0B

echo =====================================================================
echo  Qwen-Image 2.1 Uncensored - Auto Installer and Runner for RDP
echo =====================================================================
echo.

:: =====================================================================
:: 1. GITHUB REPOSITORY CONFIGURATION
:: =====================================================================
set "REPO_URL=https://github.com/guravnarendra/qwenrepo.git"
set "CLONE_DIR=qwenrepo"

:: Check if run.py exists in the current directory or a subfolder
if not exist "run.py" (
    if exist "%CLONE_DIR%\run.py" (
        cd /d "%CLONE_DIR%"
        call run_on_rdp.bat
        exit /b 0
    ) else (
        echo [INFO] Project files not found in current folder.
        echo Checking Git to clone repository from GitHub...
        echo.
    )
)

:: =====================================================================
:: 2. CHECK / INSTALL GIT (OPTIONAL)
:: =====================================================================
where git >nul 2>nul
if !errorlevel! neq 0 (
    echo [1/6] Git is not detected. Attempting automatic install...
    curl.exe -L -o "%TEMP%\git_installer.exe" "https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe"
    if exist "%TEMP%\git_installer.exe" (
        echo Installing Git silently...
        start /wait "" "%TEMP%\git_installer.exe" /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS
        del /f /q "%TEMP%\git_installer.exe" >nul 2>nul
        set "PATH=C:\Program Files\Git\cmd;C:\Program Files (x86)\Git\cmd;%LocalAppData%\Programs\Git\cmd;!PATH!"
    )
)

where git >nul 2>nul
if !errorlevel! equ 0 (
    echo [OK] Git is available.
) else (
    echo [INFO] Git not found. Direct GitHub download mode will be used.
)
echo.

:: =====================================================================
:: 3. FETCH PROJECT FROM GITHUB (GIT OR DIRECT ZIP)
:: =====================================================================
if not exist "run.py" (
    echo [2/6] Getting project files from GitHub...
    set "FETCH_OK=0"
    
    where git >nul 2>nul
    if !errorlevel! equ 0 (
        echo Cloning repository via Git...
        git clone "!REPO_URL!" "%CLONE_DIR%"
        if exist "%CLONE_DIR%\run.py" (
            set "FETCH_OK=1"
        )
    )
    
    if "!FETCH_OK!"=="0" (
        echo Downloading repository ZIP from GitHub...
        del /f /q "%TEMP%\qwenrepo.zip" >nul 2>nul
        curl.exe -L -o "%TEMP%\qwenrepo.zip" "https://github.com/guravnarendra/qwenrepo/archive/refs/heads/main.zip"
        
        if exist "%TEMP%\qwenrepo.zip" (
            echo Extracting project files...
            tar.exe -xf "%TEMP%\qwenrepo.zip" -C . 2>nul
            if not exist "qwenrepo-main\run.py" (
                powershell -Command "Expand-Archive -Force '%TEMP%\qwenrepo.zip' '.'"
            )
            del /f /q "%TEMP%\qwenrepo.zip" >nul 2>nul
            
            if exist "qwenrepo-main" (
                if exist "%CLONE_DIR%" rmdir /s /q "%CLONE_DIR%"
                ren "qwenrepo-main" "%CLONE_DIR%"
                set "FETCH_OK=1"
            )
        )
    )
    
    if exist "%CLONE_DIR%\run.py" (
        echo [OK] Project ready in %CLONE_DIR%. Launching installer...
        cd /d "%CLONE_DIR%"
        call run_on_rdp.bat
        exit /b 0
    ) else (
        echo [ERROR] Could not download project files.
        pause
        exit /b 1
    )
) else (
    echo [OK] Project files verified.
    if exist ".git" (
        echo Checking for latest updates...
        git pull --quiet 2>nul
    )
)
echo.

:: =====================================================================
:: 4. CHECK / INSTALL PYTHON
:: =====================================================================
set "PYTHON_CMD="
del /f /q "%TEMP%\pyver.txt" >nul 2>nul
python --version >"%TEMP%\pyver.txt" 2>nul
if exist "%TEMP%\pyver.txt" (
    set /p PY_VER=<"%TEMP%\pyver.txt"
    del /f /q "%TEMP%\pyver.txt" >nul 2>nul
    if not "!PY_VER!"=="" set "PYTHON_CMD=python"
)

if "!PYTHON_CMD!"=="" (
    py --version >"%TEMP%\pyver.txt" 2>nul
    if exist "%TEMP%\pyver.txt" (
        set /p PY_VER=<"%TEMP%\pyver.txt"
        del /f /q "%TEMP%\pyver.txt" >nul 2>nul
        if not "!PY_VER!"=="" set "PYTHON_CMD=py"
    )
)

if "!PYTHON_CMD!"=="" (
    echo [3/6] Python is NOT installed. Installing Python 3.10.11 silently...
    echo Downloading official Python installer...
    
    del /f /q "%TEMP%\python_installer.exe" >nul 2>nul
    curl.exe -L -o "%TEMP%\python_installer.exe" "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
    
    if not exist "%TEMP%\python_installer.exe" (
        echo [ERROR] Failed to download Python installer!
        echo Please install Python 3.10 manually from https://www.python.org/
        pause
        exit /b 1
    )
    
    echo Installing Python 3.10 and adding to PATH...
    start /wait "" "%TEMP%\python_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 SimpleInstall=1
    del /f /q "%TEMP%\python_installer.exe" >nul 2>nul
    
    set "PATH=%LocalAppData%\Programs\Python\Python310;%LocalAppData%\Programs\Python\Python310\Scripts;!PATH!"
    if exist "%LocalAppData%\Programs\Python\Python310\python.exe" (
        set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python310\python.exe"
    ) else (
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
    !PYTHON_CMD! -m venv venv
    if !errorlevel! neq 0 (
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
echo [5/6] Checking and Installing PyTorch CUDA and dependencies...

python -c "import torch; assert torch.cuda.is_available()" >nul 2>nul
if !errorlevel! neq 0 (
    echo Installing PyTorch with CUDA 12.4 support...
    python -m pip install --upgrade pip
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
    if !errorlevel! neq 0 (
        echo [WARNING] CUDA 12.4 install had issues, trying CUDA 12.1...
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
choice /c 12 /t 5 /d 1 /m "Auto-launching Web UI in 5 seconds (Press 1 or 2 to choose)"

if !errorlevel! equ 2 (
    echo.
    echo Starting Jupyter Lab...
    jupyter lab
) else (
    echo.
    echo Starting Qwen-Image 2.1 Uncensored Web UI...
    python run.py
)

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] An error occurred while running the application.
    pause
)
