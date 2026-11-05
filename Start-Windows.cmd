@echo off
cd /d "%~dp0"
if exist "dist\CaseMouse\CaseMouse.exe" (
  start "" "dist\CaseMouse\CaseMouse.exe"
) else (
  py -3.12 app.py
)
