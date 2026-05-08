' flow-st8 launcher — uses compiled EXE if available, falls back to pythonw.
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = scriptDir & "\dist\flow-st8\flow-st8.exe"
If fso.FileExists(exePath) Then
    shell.CurrentDirectory = scriptDir & "\dist\flow-st8"
    shell.Run """" & exePath & """", 0, False
Else
    shell.CurrentDirectory = scriptDir
    shell.Run "pythonw.exe """ & scriptDir & "\main.py""", 0, False
End If
