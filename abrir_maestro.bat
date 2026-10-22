@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale em python.org e marque "Add to PATH".
  pause
  exit /b 1
)
wscript "%~dp0abrir_maestro.vbs"
