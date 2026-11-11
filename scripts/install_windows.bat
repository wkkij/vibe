@echo off
cd /d "%~dp0.."
echo ======================================================
echo Installing Vibe CLI dependencies...
echo ======================================================
python -m venv .venv
if errorlevel 1 (
    echo [ERROR] Python not found in PATH! Install Python 3.10+ first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
if not exist .env copy .env.example .env
echo.
echo ======================================================
echo Installation complete!
echo Step 1: Run scripts\start_chrome_windows.bat
echo Step 2: Run run_vibe.bat
echo ======================================================
pause
