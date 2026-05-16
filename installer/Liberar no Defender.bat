@echo off
REM ============================================================
REM  Adiciona o Apresentador vMix as excecoes do Windows Defender.
REM  Use quando o Defender atrapalhar o app (falso-positivo).
REM
REM  IMPORTANTE: rode com "Executar como administrador"
REM  (clique com o botao direito neste arquivo).
REM ============================================================

powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-MpPreference -ExclusionProcess 'Iniciar Apresentador.exe'; Add-MpPreference -ExclusionProcess 'ffmpeg.exe'; Add-MpPreference -ExclusionProcess 'ffprobe.exe'"

if errorlevel 1 (
    echo.
    echo  Falhou. Clique com o botao direito neste arquivo
    echo  e escolha "Executar como administrador".
) else (
    echo.
    echo  Pronto - Apresentador vMix liberado no Defender.
)
echo.
pause
