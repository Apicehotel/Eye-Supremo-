[Setup]
AppId={{B7E2A901-4D8C-4F1A-9E33-2C8F0A1D6B44}
AppName=Ask Fatture
AppVersion=0.3.0
AppPublisher=Apicehotel
AppComments=Ask Fatture: import XML, catalogo fornitori/prodotti, pack Chili/Litri/Pezzi, Ollama locale
DefaultDirName={autopf}\Ask Fatture
DefaultGroupName=Ask Fatture
OutputDir=..\release
OutputBaseFilename=AskFatture-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\AskFatture.exe

[Files]
Source: "..\dist\AskFatture.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\ask-fatture\scarica-modello.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Ask Fatture"; Filename: "{app}\AskFatture.exe"
Name: "{autodesktop}\Ask Fatture"; Filename: "{app}\AskFatture.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crea un'icona sul desktop"; GroupDescription: "Collegamenti:"

[Run]
Filename: "{app}\AskFatture.exe"; Description: "Avvia Ask Fatture"; Flags: nowait postinstall skipifsilent

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
      'Ask Fatture e'' un''app a finestra nativa e richiede Microsoft Edge WebView2.'#13#10#13#10 +
      'Su Windows 10/11 aggiornato e'' di solito gia'' installato. Se manca, installalo da:'#13#10 +
      'https://developer.microsoft.com/microsoft-edge/webview2/',
      mbInformation, MB_OK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: string;
begin
  if CurStep = ssPostInstall then
  begin
    DataDir := ExpandConstant('{localappdata}\AskFatture');
    ForceDirectories(DataDir);
    ForceDirectories(DataDir + '\uploads');
  end;
end;
