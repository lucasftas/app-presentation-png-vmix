; Instalador do Apresentador vMix (Inno Setup 6).
;
; Empacota a pasta --onedir gerada por scripts\build.bat
; (dist\Iniciar Apresentador\) num unico Setup.exe.
;
; Instala em %LocalAppData%\Apresentador vMix SEM exigir admin (UAC):
; - pasta gravavel -> config.json e logs\ funcionam ao lado do exe
; - sem extracao em %TEMP% (--onedir carrega de _internal\), entao o crash de
;   temp do --onefile nao acontece mais.
;
; Compilar: installer\build-installer.bat (acha o ISCC.exe e roda este script).

#define AppName "Apresentador vMix"
#define AppExe "Iniciar Apresentador.exe"
#define AppVersion "1.2.0"
#define SrcDir "..\dist\Iniciar Apresentador"

[Setup]
AppId={{A3F1C2D4-5E6B-47A8-9C10-2B4D6E8F0A12}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Facial Academy
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
; Sem admin: instala no perfil do usuario. Pasta gravavel pro config/logs.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Apresentador vMix Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"
Name: "defenderexcl"; Description: "Adicionar exclusão no Windows Defender (recomendado — pede confirmação de admin)"; GroupDescription: "Antivírus:"; Flags: unchecked

[Files]
; Pasta inteira do --onedir (exe + _internal\ com dll/ffmpeg/html/icones).
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Helper pra liberar no Defender manualmente depois, se o usuario quiser.
Source: "Liberar no Defender.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "LEIA-ME.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Exclusao no Defender (so se o usuario marcou a task): roda o .bat elevado
; via Start-Process -Verb RunAs — dispara UAC so pra essa acao, sem exigir que
; o instalador inteiro seja admin.
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Start-Process -FilePath '{app}\Liberar no Defender.bat' -Verb RunAs"""; \
  Flags: runhidden waituntilterminated; Tasks: defenderexcl; StatusMsg: "Adicionando exclusão no Windows Defender..."
; Abrir o app ao terminar (checkbox no fim do wizard).
Filename: "{app}\{#AppExe}"; Description: "Iniciar o {#AppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove dados gerados ao lado do exe (config e logs ficam no install dir).
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\_kiosk_cache"
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\config.bak.json"
