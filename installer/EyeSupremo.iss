[Setup]
AppId={{8C37D550-5C55-4D3F-9BF0-79B452FA9E73}
AppName=Eye Supremo
AppVersion=1.3.0
AppPublisher=Apicehotel
DefaultDirName={autopf}\Eye Supremo
DefaultGroupName=Eye Supremo
OutputDir=..\release
OutputBaseFilename=EyeSupremo-Setup
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
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Eye Supremo"; Filename: "{app}\EyeSupremo.exe"
Name: "{autodesktop}\Eye Supremo"; Filename: "{app}\EyeSupremo.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crea un'icona sul desktop"; GroupDescription: "Collegamenti:"

[Run]
Filename: "{app}\EyeSupremo.exe"; Description: "Avvia Eye Supremo"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir, EnvSrc, EnvDst: string;
begin
  if CurStep = ssPostInstall then
  begin
    DataDir := ExpandConstant('{localappdata}\EyeSupremo');
    ForceDirectories(DataDir);
    EnvSrc := ExpandConstant('{app}\.env.example');
    EnvDst := DataDir + '\.env';
    if (not FileExists(EnvDst)) and FileExists(EnvSrc) then
      FileCopy(EnvSrc, EnvDst, False);
  end;
end;
