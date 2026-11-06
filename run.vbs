' 无控制台窗口启动 Muse。
' 前提：pythonw.exe 在 PATH 里（安装 Python 时勾选 Add Python to PATH）。
Option Explicit
Dim fso, shell, base
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = base
shell.Run "pythonw.exe """ & base & "\main.py""", 0, False
