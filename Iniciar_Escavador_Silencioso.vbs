Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Obtém a pasta atual onde o script VBScript está localizado de forma dinâmica
ScriptPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptPath

' Define a variável de ambiente SILENT_MODE para que o Python saiba que foi iniciado pelo script silencioso
WshShell.Environment("Process").Item("SILENT_MODE") = "1"

' Função para registrar logs de depuração silenciosamente
Sub LogMsg(msg)
    On Error Resume Next
    Dim logDir, logFile, f
    logDir = ScriptPath & "\logs"
    If Not fso.FolderExists(logDir) Then
        fso.CreateFolder(logDir)
    End If
    logFile = logDir & "\vbs_debug.log"
    Set f = fso.OpenTextFile(logFile, 8, True) ' 8 = ForAppending
    f.WriteLine Now & " - " & msg
    f.Close
    On Error GoTo 0
End Sub

LogMsg "Iniciando script silencioso..."

' 1. Cria ou Atualiza o atalho na Área de Trabalho do usuário atual automaticamente
DesktopPath = WshShell.SpecialFolders("Desktop")
shortcutLnk = DesktopPath & "\Escavador de Pend" & ChrW(234) & "ncias e-CAC.lnk"

On Error Resume Next
Set shortcut = WshShell.CreateShortcut(shortcutLnk)
shortcut.TargetPath = "wscript.exe"
shortcut.Arguments = """" & ScriptPath & "\Iniciar_Escavador_Silencioso.vbs"""
shortcut.WorkingDirectory = ScriptPath
shortcut.IconLocation = ScriptPath & "\app_icon.ico,0"
shortcut.Save
If Err.Number <> 0 Then
    LogMsg "Erro ao criar atalho no Desktop: " & Err.Description
Else
    LogMsg "Atalho criado/atualizado com sucesso no Desktop."
End If
On Error GoTo 0

' 2. Procura o Python em caminhos comuns do usuário atual para maior robustez
Dim pythonCmd
pythonCmd = "python" ' Fallback genérico

userProfile = WshShell.ExpandEnvironmentStrings("%USERPROFILE%")
LogMsg "UserProfile obtido: " & userProfile

Dim pyPaths(2)
pyPaths(0) = userProfile & "\AppData\Local\Programs\Python\Python311\python.exe"
pyPaths(1) = userProfile & "\AppData\Local\Programs\Python\Python313\python.exe"
pyPaths(2) = "python.exe"

Dim p
For Each p In pyPaths
    LogMsg "Testando caminho: " & p
    If p = "python.exe" Then
        pythonCmd = "python"
        LogMsg "Usando fallback 'python' (p = python.exe)"
        Exit For
    ElseIf fso.FileExists(p) Then
        pythonCmd = """" & p & """"
        LogMsg "Python encontrado! Usando: " & pythonCmd
        Exit For
    Else
        LogMsg "Arquivo nao existe: " & p
    End If
Next

LogMsg "Comando final selecionado: " & pythonCmd

' 3. Verifica se o servidor Flask já está rodando na porta 5000
On Error Resume Next
Set xmlHttp = CreateObject("MSXML2.ServerXMLHTTP.6.0")
xmlHttp.open "GET", "http://127.0.0.1:5000/", False
xmlHttp.send
Dim portError
portError = Err.Number
On Error GoTo 0

LogMsg "Erro da porta 5000 (se 0, já estava ativa): " & portError

If portError <> 0 Then
    LogMsg "Iniciando Flask..."
    ' Se a porta estiver fechada, inicia o backend Flask de forma invisível
    Dim runCmd
    runCmd = pythonCmd & " app.py"
    LogMsg "Executando: " & runCmd
    WshShell.Run runCmd, 0, False
    LogMsg "Comando Run enviado."
    ' Aguarda 3 segundos para o servidor subir
    WScript.Sleep 3000
Else
    LogMsg "Servidor Flask já está ativo na porta 5000."
End If

' 4. Abre a interface no Edge em modo de aplicativo (sem barra de URL)
edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
If fso.FileExists(edgePath) Then
    edgeCmd = """" & edgePath & """ --app=http://127.0.0.1:5000/"
    LogMsg "Abrindo no Edge (App Mode): " & edgeCmd
    WshShell.Run edgeCmd, 1, False
Else
    LogMsg "Edge não encontrado. Abrindo com navegador padrão..."
    WshShell.Run "http://127.0.0.1:5000/", 1, False
End If
LogMsg "Execução do VBScript concluída."
