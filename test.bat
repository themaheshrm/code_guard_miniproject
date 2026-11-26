@echo off
setlocal
REM Runs the backend test-suite and a production build of the frontend.
cd /d "%~dp0"
if not exist backend\.venv\Scripts\python.exe (
  echo [ERROR] Run setup.bat first.
  exit /b 1
)
pushd backend
.venv\Scripts\python.exe -m pytest || (popd & echo [FAIL] backend tests & exit /b 1)
popd
pushd frontend
call npm run build || (popd & echo [FAIL] frontend build & exit /b 1)
popd
echo All checks passed.
endlocal
