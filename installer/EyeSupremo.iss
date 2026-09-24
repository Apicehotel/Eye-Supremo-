[Setup]
AppId={{8C37D550-5C55-4D3F-9BF0-79B452FA9E73}
AppName=Eye Supremo
AppVersion=1.4.2
AppPublisher=Apicehotel
AppComments=Suite desktop: Eye Supremo + Ask Fatture + catalogo Supabase (WebView2)
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
SetupIconFile=..\assets\icons\eye-supremo.ico
InfoBeforeFile=

[Files]
; Gestionale Eye Supremo
Source: "..\dist\EyeSupremo.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scarica-modelli-ia.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion
; Ask Fatture (stesso installer)
Source: "..\dist\AskFatture.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\ask-fatture\scarica-modello.bat"; DestDir: "{app}"; DestName: "scarica-modello-ask.bat"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Eye Supremo"; Filename: "{app}\EyeSupremo.exe"
Name: "{autoprograms}\Ask Fatture"; Filename: "{app}\AskFatture.exe"
Name: "{autoprograms}\Scarica modelli IA (Ollama)"; Filename: "{app}\scarica-modelli-ia.bat"
Name: "{autoprograms}\Scarica modello Ask Fatture"; Filename: "{app}\scarica-modello-ask.bat"
Name: "{autodesktop}\Eye Supremo"; Filename: "{app}\EyeSupremo.exe"; Tasks: desktopicon
Name: "{autodesktop}\Ask Fatture"; Filename: "{app}\AskFatture.exe"; Tasks: desktopiconask

[Tasks]
Name: "desktopicon"; Description: "Icona desktop Eye Supremo"; GroupDescription: "Collegamenti:"
Name: "desktopiconask"; Description: "Icona desktop Ask Fatture"; GroupDescription: "Collegamenti:"; Flags: checkedonce

[Run]
Filename: "{app}\EyeSupremo.exe"; Description: "Avvia Eye Supremo"; Flags: nowait postinstall skipifsilent unchecked
Filename: "{app}\AskFatture.exe"; Description: "Avvia Ask Fatture"; Flags: nowait postinstall skipifsilent unchecked

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
      'Eye Supremo e Ask Fatture richiedono Microsoft Edge WebView2.'#13#10#13#10 +
      'Su Windows 10/11 aggiornato e'' di solito gia'' installato. Se manca, installalo da:'#13#10 +
      'https://developer.microsoft.com/microsoft-edge/webview2/',
      mbInformation, MB_OK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  EyeData, AskData, EnvSrc, EnvDst: string;
begin
  if CurStep = ssPostInstall then
  begin
    EyeData := ExpandConstant('{localappdata}\EyeSupremo');
    AskData := ExpandConstant('{localappdata}\AskFatture');
    ForceDirectories(EyeData);
    ForceDirectories(AskData);
    ForceDirectories(AskData + '\uploads');
    EnvSrc := ExpandConstant('{app}\.env.example');
    EnvDst := EyeData + '\.env';
    if (not FileExists(EnvDst)) and FileExists(EnvSrc) then
      FileCopy(EnvSrc, EnvDst, False);
  end;
end;
