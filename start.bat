@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No .venv found. Create it first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload
pause
