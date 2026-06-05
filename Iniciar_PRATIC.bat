@echo off
title PRATIC - Sistema de Producao
color 0A

echo.
echo  ================================
echo    PRATIC - Sistema de Producao
echo  ================================
echo.
echo  Iniciando servidor, aguarde...
echo.

cd /d "%~dp0backend"

start /b py main.py

if %errorlevel% neq 0 (
    echo.
    echo  ERRO ao iniciar o servidor!
    echo  Verifique se o Python esta instalado corretamente.
    echo.
    pause
    exit /b 1
)

echo  Aguardando servidor iniciar...
timeout /t 4 /nobreak >nul

echo  Abrindo navegador...
start "" "http://localhost:8000"

echo.
echo  Sistema iniciado! Nao feche esta janela.
echo  Para encerrar, feche esta janela ou pressione CTRL+C.
echo.
pause >nul
