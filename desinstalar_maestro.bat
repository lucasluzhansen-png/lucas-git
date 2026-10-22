@echo off
rem Desliga o Maestro. Uso: desinstalar_maestro.bat lucas   (ou recepcao)
set PERFIL=%1
if "%PERFIL%"=="" set PERFIL=lucas
schtasks /Delete /F /TN "Maestro Hansen (%PERFIL%)"
pause
