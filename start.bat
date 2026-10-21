@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import ensurepip" >nul 2>nul
if not errorlevel 1 (
  set "PYTHON=py -3"
) else (
  if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    set PYTHON="%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  ) else (
    set "PYTHON=python"
  )
)
if not exist ".venv\Scripts\python.exe" (
  %PYTHON% -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m ensurepip --upgrade
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
if not defined PORT set "PORT=5000"
echo Open http://127.0.0.1:%PORT% in your browser.
echo Keep this window open. Press Ctrl+C to stop.
".venv\Scripts\python.exe" app.py
goto end
:failed
echo Setup failed. Install standard Python 3.10+ from python.org and try again.
:end
pause
