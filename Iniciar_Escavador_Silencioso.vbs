Set WshShell = CreateObject("WScript.Shell")
' Executa o iniciar_painel.bat em modo invisível (0) e sem bloquear a execução (false)
WshShell.Run "cmd.exe /c iniciar_painel.bat", 0, false
