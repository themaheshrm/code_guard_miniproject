@echo off
setlocal
REM CodeGuard one-time setup for Windows: Python venv + backend deps, frontend deps + production build.
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo [ERROR] Python 3.10+ not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  exit /b 1
)
where npm >nul 2>nul || (
  echo [ERROR] Node.js 18+ not found. Install the LTS version from https://nodejs.org/
  exit /b 1
)

echo === [1/4] Creating Python virtual environment in backend\.venv
if not exist backend\.venv\Scripts\python.exe (
  %PY% -m venv backend\.venv || (echo [ERROR] venv creation failed & exit /b 1)
)

echo === [2/4] Installing backend dependencies
backend\.venv\Scripts\python.exe -m pip install --upgrade pip >nul
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt || (echo [ERROR] pip install failed & exit /b 1)

echo === [3/4] Installing frontend dependencies
pushd frontend
call npm install || (popd & echo [ERROR] npm install failed & exit /b 1)

echo === [4/4] Building the frontend
call npm run build || (popd & echo [ERROR] frontend build failed & exit /b 1)
popd

if not exist .env copy .env.example .env >nul
echo.
echo Setup complete. Run start.bat and open http://localhost:8000
endlocal
