Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = """" & scriptDir & "\run_app.cmd" & """"
shell.Run cmd, 0, False
