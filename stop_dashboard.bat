@echo off
echo ===========================================
echo Stopping AI Cement Dashboard...
echo ===========================================

echo 1. Stopping process using Port 8500...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8500') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo 2. Stopping process by CommandLine match...
powershell -Command "Get-CimInstance Win32_Process -Filter \"CommandLine LIKE '%%app.py%%'\" | Foreach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo.
echo Dashboard stopped.
pause
