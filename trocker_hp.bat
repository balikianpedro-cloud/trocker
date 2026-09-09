@echo off
REM Trocker no HP (CPU-only): venv fora do OneDrive em C:\Users\HP\venvs\trockerv
set "TROCKER_DIR=%~dp0"
set "VENV=C:\Users\HP\venvs\trockerv"
if not exist "%VENV%\Scripts\python.exe" (
  echo Venv nao encontrado em %VENV%. Rode: python -m venv %VENV% e pip install -r requirements.txt
  pause & exit /b 1
)
cd /d "%TROCKER_DIR%"
"%VENV%\Scripts\python.exe" src\main.py
