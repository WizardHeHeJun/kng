@echo off
setlocal
chcp 65001 >nul

set "PROJECT_ID=%~1"
set "DOC_URL=%~2"

if "%PROJECT_ID%"=="" set "PROJECT_ID=demo-game"

if "%DOC_URL%"=="" (
  echo.
  set /p DOC_URL=Please input Lark doc URL: 
)

if "%DOC_URL%"=="" (
  echo [ERROR] Empty URL, exit.
  exit /b 1
)

echo.
echo [INFO] Project ID: %PROJECT_ID%
echo [INFO] Doc URL: %DOC_URL%
echo [INFO] Running dual-KB test generation...
echo.

python "tools\dual_kb_test_agent.py" --project-id "%PROJECT_ID%" --url "%DOC_URL%"
if errorlevel 1 (
  echo.
  echo [ERROR] Failed. Check lark-cli auth, network, or OPENAI_API_KEY.
  exit /b 1
)

echo.
echo [INFO] Done. Opening test-output folder...
if not exist "test-output" (
  echo [WARN] test-output folder not found. Please check logs.
  exit /b 0
)

start "" "test-output"
exit /b 0
