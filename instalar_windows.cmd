@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Instala Python 3.12 de 64 bits con el lanzador py y vuelve a intentarlo.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install -r requirements-windows.txt
if errorlevel 1 (
  echo No se pudo completar la instalacion. Revisa la conexion y los mensajes.
  pause
  exit /b 1
)
echo Instalacion completada. Abre iniciar_objetos.cmd.
pause
