@echo off
rem Liga o Maestro: roda a cada 15 minutos, sem janela. Uso: instalar_maestro.bat lucas   (ou recepcao)
set PERFIL=%1
if "%PERFIL%"=="" set PERFIL=lucas
schtasks /Create /F /SC MINUTE /MO 15 /TN "Maestro Hansen (%PERFIL%)" /TR "wscript.exe \"%~dp0maestro_tick.vbs\" %PERFIL%"
if errorlevel 1 (echo. & echo NAO FOI POSSIVEL AGENDAR. Tente abrir este arquivo como Administrador.) else (echo. & echo Pronto! O Maestro vai cobrar a cada 15 minutos, de segunda a sexta, das 8h as 18h.)
pause
