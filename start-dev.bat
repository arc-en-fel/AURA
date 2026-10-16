@echo off
setlocal enabledelayedexpansion

rem Resolve the repository root from this script so it works from any current directory.
set "ROOT=%~dp0"

echo ===================================================
echo   AURA Self-Evolving CRM - Development Launcher
echo ===================================================
echo.

rem Verify backend virtual environment
if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
    echo [ERROR] Backend virtual environment not found at:
    echo   "%ROOT%backend\.venv"
    echo.
    echo Please create the virtual environment and install dependencies:
    echo   cd /d "%ROOT%backend"
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

rem Verify frontend node_modules
if not exist "%ROOT%frontend\node_modules" (
    echo [ERROR] Frontend dependencies not found at:
    echo   "%ROOT%frontend\node_modules"
    echo.
    echo Please install dependencies:
    echo   cd /d "%ROOT%frontend"
    echo   npm install
    echo.
    pause
    exit /b 1
)

echo Starting FastAPI Backend on http://localhost:8000...
rem Start backend using /d working directory to avoid nested quote corruption on Windows paths with spaces
start "AURA Backend" cmd /k "cd /d "%ROOT%backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

echo Starting Vite Frontend on http://localhost:5173...
start "AURA Frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

echo.
echo Both servers launched in separate terminal windows.
echo Frontend: http://localhost:5173
echo Backend:  http://localhost:8000/api/v1/health
echo Swagger:  http://localhost:8000/docs
echo.

endlocal

