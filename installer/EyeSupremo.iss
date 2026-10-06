[Setup]
AppId={{8C37D550-5C55-4D3F-9BF0-79B452FA9E73}
AppName=Eye Supremo
AppVersion=2.0.0
AppPublisher=Apicehotel
DefaultDirName={autopf}\Eye Supremo
DefaultGroupName=Eye Supremo
OutputDir=..\release
OutputBaseFilename=EyeSupremo-Setup
SetupIconFile=assets\eye-supremo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\EyeSupremo.exe

[Files]
Source: "..\dist\EyeSupremo.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scarica-modelli-ia.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Eye Supremo"; Filename: "{app}\EyeSupremo.exe"
Name: "{autodesktop}\Eye Supremo"; Filename: "{app}\EyeSupremo.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crea un'icona sul desktop"; GroupDescription: "Collegamenti:"

[Run]
Filename: "{cmd}"; Parameters: "/c ""{app}\scarica-modelli-ia.bat"" /silent"; Description: "Installa Ollama e i modelli IA locali (Qwen + Llama)"; StatusMsg: "Installazione modelli IA in corso..."; Flags: waituntilterminated
Filename: "{app}\EyeSupremo.exe"; Description: "Avvia Eye Supremo"; Flags: nowait postinstall skipifsilent
