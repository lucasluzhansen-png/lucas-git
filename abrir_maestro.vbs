' Abre o Maestro sem janela preta.
Set sh = CreateObject("WScript.Shell")
pasta = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = pasta
sh.Environment("Process")("PYTHONPATH") = pasta & "\src"
sh.Run "cmd /c pythonw -m hansen.app > """ & pasta & "\app.log"" 2>&1", 0, False
