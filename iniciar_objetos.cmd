@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecuta instalar_windows.cmd.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m aula_ia.object_desktop
if errorlevel 1 pause
