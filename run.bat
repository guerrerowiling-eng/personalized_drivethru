@echo off
setlocal
cd /d "%~dp0"
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Create it with: python -m venv venv
    exit /b 1
)
call "%~dp0venv\Scripts\activate.bat"
python app.py
exit /b %ERRORLEVEL%
