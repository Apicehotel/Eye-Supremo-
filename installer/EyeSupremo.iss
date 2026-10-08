[Setup]
AppId={{8C37D550-5C55-4D3F-9BF0-79B452FA9E73}
AppName=Eye Supremo
AppVersion=2.0.2
AppPublisher=Apicehotel
AppComments=Applicazione desktop nativa Windows (WebView2), non un sito nel browser
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
      'Eye Supremo e'' un''app Windows a finestra nativa e richiede Microsoft Edge WebView2.'#13#10#13#10 +
      'Su Windows 10/11 aggiornato e'' di solito gia'' presente. Se manca, installalo da:'#13#10 +
      'https://developer.microsoft.com/microsoft-edge/webview2/',
      mbInformation, MB_OK);
  end;
end;
