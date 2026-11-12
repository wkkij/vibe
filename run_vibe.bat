@echo off
cd /d "%~dp0"
rem Inside the classic console window the mascot can only be drawn with symbols. Windows Terminal can show it as a real picture,
rem so if it is installed, restart this script there (set VIBE_NO_WT=1 to skip that).
if not defined WT_SESSION if not defined VIBE_NO_WT (
    where wt.exe >nul 2>nul
    if not errorlevel 1 (
        start "" wt.exe -d "%~dp0." cmd /c ""%~f0" %*"
        exit /b
    )
)
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe vibe.py %*
) else (
    python vibe.py %*
)
pause

