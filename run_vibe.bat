@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe vibe.py %*
) else (
    python vibe.py %*
)
pause
