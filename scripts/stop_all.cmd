@echo off
setlocal
cd /d "%~dp0.."

set "PID_DIR=tmp\launcher"
set "STOPPED_ANY="

echo Stopping launcher-managed Research Assistant services...

call :stop_process backend "Backend API"
call :stop_process frontend "Next.js frontend"

if defined STOPPED_ANY (
    echo Done.
) else (
    echo No launcher-managed services were found.
    echo This script does not stop unrelated applications on ports 8000 or 3000.
)

pause
exit /b 0

:stop_process
set "SERVICE_NAME=%~1"
set "SERVICE_LABEL=%~2"
set "PID_FILE=%PID_DIR%\%SERVICE_NAME%.pid"

if not exist "%PID_FILE%" (
    echo %SERVICE_LABEL%: no PID file found.
    goto :eof
)

set /p TARGET_PID=<"%PID_FILE%"
if not defined TARGET_PID (
    del /q "%PID_FILE%" >nul 2>nul
    echo %SERVICE_LABEL%: removed empty PID file.
    goto :eof
)

tasklist /FI "PID eq %TARGET_PID%" | findstr /I "%TARGET_PID%" >nul
if errorlevel 1 (
    echo %SERVICE_LABEL%: process %TARGET_PID% is not running.
) else (
    echo %SERVICE_LABEL%: stopping PID %TARGET_PID%...
    taskkill /F /T /PID %TARGET_PID% >nul 2>nul
    set "STOPPED_ANY=1"
)

del /q "%PID_FILE%" >nul 2>nul
goto :eof
