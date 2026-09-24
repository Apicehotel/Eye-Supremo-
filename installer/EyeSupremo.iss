[Setup]
AppId={{8C37D550-5C55-4D3F-9BF0-79B452FA9E73}
AppName=Eye Supremo
AppVersion=1.3.1
AppPublisher=Apicehotel
AppComments=Applicazione desktop nativa (WebView2) per fatture Eye Supremo
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
function WebView2Installed: Boolean;
begin
  Result :=
    RegKeyExists(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') or
    RegKeyExists(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') or
    RegKeyExists(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}');
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not WebView2Installed then
  begin
    MsgBox(
      'Eye Supremo e'' un''app a finestra nativa e richiede Microsoft Edge WebView2.'#13#10#13#10 +
      'Su Windows 10/11 aggiornato e'' di solito gia'' installato. Se manca, installalo da:'#13#10 +
      'https://developer.microsoft.com/microsoft-edge/webview2/',
      mbInformation, MB_OK);
  end;
end;

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
