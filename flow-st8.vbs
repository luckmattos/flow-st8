' flow-st8 launcher - runs pythonw.exe main.py with zero visible windows.
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir
shell.Run "pythonw.exe """ & scriptDir & "\main.py""", 0, False
