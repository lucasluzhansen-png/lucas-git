' Roda um ciclo do Maestro SEM abrir janela. Uso: wscript maestro_tick.vbs lucas|recepcao
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
perfil = "lucas"
If WScript.Arguments.Count > 0 Then perfil = WScript.Arguments(0)
sh.Run "cmd /c set PYTHONPATH=src&& set PYTHONIOENCODING=utf-8&& python -m hansen.maestro_vivo --perfil " & perfil, 0, False
