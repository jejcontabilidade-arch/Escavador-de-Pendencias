@echo off
title J^&J Contabilidade - Escavador de Pendencias e-CAC (Painel Web)
chcp 65001 > NUL

echo ======================================================================
echo           J^&J CONTABILIDADE - ESCAVADOR DE PENDENCIAS E-CAC
echo                   INICIALIZADOR DO PAINEL WEB
echo ======================================================================
echo.

:: Verificar se o Python esta no PATH
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] O Python nao foi encontrado no sistema ou nao esta no PATH.
    echo Por favor, instale o Python 3 e marque a opcao "Add Python to PATH" na instalacao.
    echo.
    pause
    exit /b
)

echo [1/2] Verificando e instalando dependencias necessarias...
echo Isso pode levar alguns segundos na primeira execucao...
python -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [AVISO] Ocorreu um erro menor ao tentar instalar dependencias.
    echo Tentando executar o Painel Web mesmo assim...
) else (
    echo [SUCESSO] Dependencias verificadas/instaladas com exito!
)

echo.
echo [2/2] Iniciando o servidor do Painel Web local...
echo O seu navegador de internet padrao abrira automaticamente em breve.
echo.
echo Para fechar o Painel, basta fechar esta janela preta do prompt de comando.
echo ----------------------------------------------------------------------
echo.

python app.py

pause
