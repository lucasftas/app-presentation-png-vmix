@echo off
REM Build do apresentador.exe via PyInstaller.
REM Saida: dist\apresentador.exe + index.html + config.example.json

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

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist apresentador.spec del apresentador.spec

pyinstaller --onefile --name apresentador --distpath dist --workpath build --clean -y src\server.py
if errorlevel 1 (
    echo [ERRO] Falha na compilacao.
    popd
    pause
    exit /b 1
)

copy /y src\index.html dist\ >nul
copy /y src\admin.html dist\ >nul
copy /y config.example.json dist\ >nul

echo.
echo ============================================================
echo  Build concluido. Distribuir a pasta dist\:
dir /b dist
echo ============================================================

popd
pause
