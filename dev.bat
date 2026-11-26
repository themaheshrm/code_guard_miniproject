@echo off
REM Development mode: API with auto-reload on :8000 and Vite hot-reload UI on :5173, each in its own window.
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe (
  echo [ERROR] Run setup.bat first.
  exit /b 1
)
start "CodeGuard API" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
start "CodeGuard UI" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 4 >nul
start "" "http://localhost:5173"
