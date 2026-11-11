@echo off
echo ============================================================================
echo Starting Chrome on port 9223 for Vibe CLI (Claude)
echo ============================================================================
echo 1. A dedicated Chrome window will open now.
echo 2. Log in to your Claude account at https://claude.ai/new
echo 3. Keep that Chrome window open while using Vibe CLI.
echo.
set "PROFILE_DIR=%USERPROFILE%\.vibe_chrome_profile_claude"
set "CHROME_EXE="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if defined CHROME_EXE goto :launch
echo [ERROR] chrome.exe not found in standard paths.
pause
exit /b 1
:launch
echo Found Chrome: "%CHROME_EXE%"
start "" "%CHROME_EXE%" --remote-debugging-port=9223 --user-data-dir="%PROFILE_DIR%" "https://claude.ai/new"
