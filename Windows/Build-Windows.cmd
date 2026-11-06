@echo off
setlocal
cd /d "%~dp0"
py -3.12 -c "import PyInstaller"
if errorlevel 1 (
  echo Install PyInstaller 6.17.0 in your chosen Python environment first.
  exit /b 1
)
py -3.12 -m PyInstaller --noconfirm --windowed --onedir --name AirPointer-Windows --add-data "orientation.mjs;." --add-data "../Sources/AirPointer/Session/Orientation.js;." app.py
