' TradePilot hidden launcher: receives an existing PowerShell -EncodedCommand.
' WScript (wscript.exe) runs without a visible console. No scheduling logic here.
Option Explicit
Dim shell, encoded, command, exitCode
If WScript.Arguments.Count <> 1 Then
    WScript.Quit 2
End If
encoded = WScript.Arguments(0)
If Len(encoded) = 0 Then
    WScript.Quit 2
End If
Set shell = CreateObject("WScript.Shell")
command = "powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand " & encoded
exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode
