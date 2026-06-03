@echo off
REM Build do Apresentador vMix - PASTA --onedir (NAO mais --onefile).
REM Tudo embutido: app + index.html + admin.html + icone + ffmpeg + ffprobe.
REM Saida: dist\Iniciar Apresentador\  (pasta com o exe + _internal\)
REM
REM Por que --onedir e nao --onefile: o --onefile extrai ~95 MB (incl. ffmpeg)
REM pra %TEMP%\_MEIxxxx A CADA boot. Antivirus/permissao/disco cheio nesse temp
REM derrubavam o app em producao. --onedir carrega de _internal\ direto -> ZERO
REM extracao em %TEMP%. A pasta e empacotada num instalador (installer\*.iss).
REM config.json e logs\ ficam ao lado do exe na pasta instalada (%LocalAppData%).

pushd "%~dp0.."
set "ROOT=%CD%"

where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [ERRO] PyInstaller nao encontrado. Instale com: pip install pyinstaller
    popd
    pause
    exit /b 1
)

if not exist "%ROOT%\assets\icon.ico" (
    echo [aviso] assets\icon.ico nao existe - gerando...
    python "%ROOT%\scripts\gerar_icone.py"
)

REM Localiza ffmpeg/ffprobe pra embutir no exe (frame de video do input List)
set "FFMPEG="
set "FFPROBE="
for /f "delims=" %%F in ('where ffmpeg 2^>nul') do if not defined FFMPEG set "FFMPEG=%%F"
for /f "delims=" %%F in ('where ffprobe 2^>nul') do if not defined FFPROBE set "FFPROBE=%%F"
if not defined FFMPEG (
    echo [ERRO] ffmpeg nao encontrado no PATH. Instale: winget install Gyan.FFmpeg
    popd
    pause
    exit /b 1
)
if not defined FFPROBE (
    echo [ERRO] ffprobe nao encontrado no PATH. Vem junto com o ffmpeg.
    popd
    pause
    exit /b 1
)
echo  ffmpeg : %FFMPEG%
echo  ffprobe: %FFPROBE%

REM Limpa builds anteriores
if exist "%ROOT%\dist" rmdir /s /q "%ROOT%\dist"
if exist "%ROOT%\build" rmdir /s /q "%ROOT%\build"

REM Compila pasta --onedir - recursos embutidos via --add-data / --add-binary.
REM Caminhos absolutos: PyInstaller resolve --add-data relativo ao --specpath.
REM --noconsole: a UI e o icone na bandeja, sem janela preta.
pyinstaller --onedir --name "Iniciar Apresentador" --icon "%ROOT%\assets\icon.ico" --noconsole --paths "%ROOT%\src" --hidden-import pystray._win32 --hidden-import PIL.Image --hidden-import PIL.IcoImagePlugin --hidden-import tkinter --hidden-import tkinter.simpledialog --add-data "%ROOT%\src\tray.py;." --add-data "%ROOT%\src\index.html;." --add-data "%ROOT%\src\admin.html;." --add-data "%ROOT%\assets\icon.ico;." --add-data "%ROOT%\assets\icon_alert.ico;." --add-binary "%FFMPEG%;." --add-binary "%FFPROBE%;." --distpath "%ROOT%\dist" --workpath "%ROOT%\build" --specpath "%ROOT%\build" --clean -y "%ROOT%\src\server.py"
if errorlevel 1 (
    echo [ERRO] Falha na compilacao.
    popd
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Build concluido - PASTA --onedir:
echo    dist\Iniciar Apresentador\Iniciar Apresentador.exe
echo    dist\Iniciar Apresentador\_internal\  (dll, ffmpeg, html...)
echo.
echo  Proximo passo: gerar o instalador com
echo    installer\build-installer.bat
echo  (empacota a pasta num Setup.exe que instala em %%LocalAppData%%).
echo.
echo  Pra testar sem instalar: rode o exe direto da pasta dist\.
echo ============================================================

popd
pause
