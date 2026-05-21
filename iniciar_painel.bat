@echo off
title J&J Contabilidade - Escavador de Pendências e-CAC (Painel Web)
chcp 65001 > NUL

echo ======================================================================
echo           J&J CONTABILIDADE - ESCAVADOR DE PENDÊNCIAS E-CAC
echo                   INICIALIZADOR DO PAINEL WEB
echo ======================================================================
echo.

:: Verificar se o Python está no PATH
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] O Python não foi encontrado no sistema ou não está no PATH.
    echo Por favor, instale o Python 3 e marque a opção "Add Python to PATH" na instalação.
    echo.
    pause
    exit /b
)

echo [1/2] Verificando e instalando dependências necessárias...
echo Isso pode levar alguns segundos na primeira execução...
python -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [AVISO] Ocorreu um erro menor ao tentar instalar dependências.
    echo Tentando executar o Painel Web mesmo assim...
) else (
    echo [SUCESSO] Dependências verificadas/instaladas com êxito!
)

echo.
echo [2/2] Iniciando o servidor do Painel Web local...
echo O seu navegador de internet padrão abrirá automaticamente em breve.
echo.
echo Para fechar o Painel, basta fechar esta janela preta do prompt de comando.
echo ----------------------------------------------------------------------
echo.

python app.py

pause
