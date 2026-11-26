@echo off
setlocal
REM Starts CodeGuard (API + built UI) on http://localhost:8000
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe (
  echo [ERROR] Run setup.bat first.
  exit /b 1
)
if not exist frontend\dist\index.html (
  echo [WARN] frontend\dist not found - building the UI first...
  pushd frontend & call npm run build & popd
)
set "PORT=8000"
if not "%~1"=="" set "PORT=%~1"
echo Starting CodeGuard on http://localhost:%PORT%   (press Ctrl+C to stop)
start "" "http://localhost:%PORT%"
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
endlocal
