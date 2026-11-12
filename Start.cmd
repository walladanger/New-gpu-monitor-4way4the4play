@echo off
cd /d "%~dp0"
where python.exe >nul 2>&1
if not errorlevel 1 (
    python.exe -c "import PIL, tkinter" >nul 2>&1
    if errorlevel 1 (
        echo This version needs Python with tkinter and Pillow.
        echo To install Pillow: python -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)
where pythonw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0Launch.pyw"
    exit /b
)
where pyw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pyw.exe -3 "%~dp0Launch.pyw"
    exit /b
)
echo Python 3.11 or later with tkinter is required.
echo Install Python from https://www.python.org/downloads/windows/ and try again.
pause
