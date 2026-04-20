@echo off
REM Build do apresentador portable.
REM Saida final: dist\Apresentador vMix\ — pasta amigavel pra leigo
REM   + Iniciar Apresentador.exe  (com icone embutido)
REM   + LEIA-ME.txt
REM   + config.json (pre-preenchido)
REM   + recursos\   (admin.html, index.html, icon.ico)

chcp 65001 >nul
pushd "%~dp0.."

where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [ERRO] PyInstaller nao encontrado. Instale com:
    echo     pip install pyinstaller
    popd
    pause
    exit /b 1
)

if not exist assets\icon.ico (
    echo [aviso] assets\icon.ico nao existe — gerando...
    python scripts\gerar_icone.py
)

REM Limpa builds anteriores
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist "Iniciar Apresentador.spec" del "Iniciar Apresentador.spec"
if exist apresentador.spec del apresentador.spec

REM Compila o .exe (single-file, com icone)
pyinstaller --onefile ^
    --name "Iniciar Apresentador" ^
    --icon assets\icon.ico ^
    --distpath dist\tmp ^
    --workpath build ^
    --specpath build ^
    --clean -y src\server.py
if errorlevel 1 (
    echo [ERRO] Falha na compilacao.
    popd
    pause
    exit /b 1
)

REM Monta a estrutura amigavel: dist\Apresentador vMix\
set "DEST=dist\Apresentador vMix"
mkdir "%DEST%"
mkdir "%DEST%\recursos"

move "dist\tmp\Iniciar Apresentador.exe" "%DEST%\" >nul
copy /y src\index.html "%DEST%\recursos\" >nul
copy /y src\admin.html "%DEST%\recursos\" >nul
copy /y assets\icon.ico "%DEST%\recursos\" >nul
copy /y installer\LEIA-ME.txt "%DEST%\" >nul
copy /y config.example.json "%DEST%\config.json" >nul

rmdir /s /q dist\tmp

echo.
echo ============================================================
echo  Build concluido. Distribuir a pasta:
echo    %DEST%\
echo.
dir /b "%DEST%"
echo.
echo  recursos\:
dir /b "%DEST%\recursos"
echo ============================================================

popd
pause
