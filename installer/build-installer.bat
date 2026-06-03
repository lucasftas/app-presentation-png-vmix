@echo off
REM ============================================================
REM  Gera o instalador do Apresentador vMix (Setup.exe).
REM
REM  1) Roda scripts\build.bat (PyInstaller --onedir)
REM  2) Acha o ISCC.exe (compilador do Inno Setup 6)
REM  3) Compila installer\apresentador.iss
REM
REM  Saida: dist\Apresentador vMix Setup.exe
REM ============================================================

pushd "%~dp0.."
set "ROOT=%CD%"

REM --- 1) Build da pasta --onedir ---
echo [1/3] Compilando o app (PyInstaller --onedir)...
call "%ROOT%\scripts\build.bat" < nul
if not exist "%ROOT%\dist\Iniciar Apresentador\Iniciar Apresentador.exe" (
    echo [ERRO] Build nao gerou dist\Iniciar Apresentador\Iniciar Apresentador.exe
    popd
    pause
    exit /b 1
)

REM --- 2) Localiza o ISCC.exe ---
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo [ERRO] ISCC.exe nao encontrado. Instale o Inno Setup 6:
    echo        winget install JRSoftware.InnoSetup
    popd
    pause
    exit /b 1
)
echo  ISCC: %ISCC%

REM --- 3) Compila o instalador ---
echo [2/3] Compilando o instalador (Inno Setup)...
"%ISCC%" "%ROOT%\installer\apresentador.iss"
if errorlevel 1 (
    echo [ERRO] Falha ao compilar o instalador.
    popd
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  [3/3] Instalador pronto:
echo    dist\Apresentador vMix Setup.exe
echo.
echo  Instala em %%LocalAppData%%\Apresentador vMix (sem admin).
echo ============================================================
popd
pause
