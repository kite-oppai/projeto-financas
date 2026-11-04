@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -File "%~dp0run_mobile.ps1"
exit /b %errorlevel%
