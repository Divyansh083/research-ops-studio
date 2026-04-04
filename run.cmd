@echo off
setlocal
cd /d "%~dp0"
echo.
echo ======================================================================
echo ======================================================================
echo           Multi-Agent Research Assistant (Batch Startup)
echo ======================================================================
echo.
echo NOTE: Please ensure no other terminals are running this project's launcher.
echo       'scripts\stop_all.cmd' only stops launcher-managed services.
echo.

REM 1. Activate venv if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM 2. Run the Python orchestrator
echo Launching services...
set CMD_ARGS=
if "%1"=="clean" (
    set CMD_ARGS=--clean
)
python scripts/run_all.py %CMD_ARGS%

pause
