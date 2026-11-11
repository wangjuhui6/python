@echo off
cd /d "%~dp0"
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw fill_excel.py
    exit /b
)
start "" python fill_excel.py
