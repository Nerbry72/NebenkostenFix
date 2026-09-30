; Installer von NebenkostenFix (NK-079, NK-155, D-84, D-95, F-82). Inno Setup 6.
;
;   iscc /DAppVersion=0.10.0 packaging\windows\installer.iss
;
; Erwartet das PyInstaller-Ergebnis unter dist\NebenkostenFix\ (Wurzel
; des Repos). Optional:
;   /DWebView2Bootstrapper=<Pfad>  MicrosoftEdgeWebview2Setup.exe beilegen
;   /DSignTool=<Name>              signieren (NK-143; SignTool in iscc/ISCmd
;                                  mit /S<Name>=... anmelden)
;   /DAppName=… /DAppExe=… /DOrdner=… /DQuelle=…
;                                  nur für die Update-Probe der CI: baut eine
;                                  „Vorversion“ mit den Namen vor NK-155
;
; Was der Installer verspricht (D-84):
; - Programm nach C:\Program Files\NebenkostenFix, Startmenü, Desktop-
;   Symbol wahlweise, kein Konsolenfenster.
; - Daten nie im Programmordner: Vorgabe Dokumente\NebenkostenFix, auf
;   einer eigenen Seite änderbar. Liegt der Ordner in OneDrive, rät der
;   Installer zu einem lokalen Ort (F-82). Die Wahl steht in
;   %LOCALAPPDATA%\NebenkostenFix\einstellungen.ini; die App liest sie
;   (windows_ordner.einstellungen_lesen).
; - D-95: Eine Installation aus der Zeit vor der Umbenennung
;   („Nebenkostenabrechnung“) behält Programm- und Datenordner; die alte Exe
;   und die alten Verknüpfungen werden ersetzt, der Datenordner aus der alten
;   einstellungen.ini übernommen.
; - Update = derselbe Installer mit höherer Version über die bestehende
;   Installation (gleiche AppId, NK-081). Die Daten bleiben, wo sie sind.
; - Deinstallation entfernt nur das Programm und sagt, wo die Daten liegen.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppName
  #define AppName "NebenkostenFix"
#endif
#ifndef AppExe
  #define AppExe "NebenkostenFix.exe"
#endif
#ifndef Quelle
  #define Quelle "..\..\dist\NebenkostenFix"
#endif
; Name des lokalen Ordners (%LOCALAPPDATA%) und des Vorgabe-Datenordners.
#ifndef Ordner
  #define Ordner "NebenkostenFix"
#endif
; Namen vor der Umbenennung (D-95).
#define AlterOrdner "Nebenkostenabrechnung"
#define AlteExe "Nebenkostenabrechnung.exe"

[Setup]
; Die AppId bleibt für alle Versionen gleich -- daran erkennt Windows das
; Update. Nie ändern.
AppId={{6F1B2C4E-8D3A-4F7B-9E21-4C5D6A7B8C9D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=NebenkostenFix
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\..\dist
OutputBaseFilename={#AppName}-{#AppVersion}-Setup
SetupIconFile=nebenkostenfix.ico
WizardImageFile=installer-gross.bmp,installer-gross-2x.bmp
WizardSmallImageFile=installer-klein.bmp,installer-klein-2x.bmp
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
; Laeuft die App noch, schliesst der Installer sie ueber den Restart Manager
; (die App schreibt beim Beenden ihr WAL zurueck).
CloseApplications=yes
RestartApplications=no
#ifdef SignTool
SignTool={#SignTool}
SignedUninstaller=yes
#endif

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Symbol auf dem Desktop anlegen"; GroupDescription: "Zusätzliche Symbole:"; Flags: unchecked

[Files]
Source: "{#Quelle}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; GPL-3.0: der Lizenztext reist mit dem Programm.
Source: "..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
; NK-148: die Lizenztexte der mitgelieferten Software auch sichtbar im
; Programmordner, nicht nur unter _internal.
Source: "{#Quelle}\_internal\THIRD_PARTY_LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion
#ifdef WebView2Bootstrapper
Source: "{#WebView2Bootstrapper}"; DestDir: "{tmp}"; DestName: "MicrosoftEdgeWebview2Setup.exe"; Flags: deleteafterinstall; Check: WebView2Fehlt
#endif

[InstallDelete]
; D-95: nach dem Update über eine Installation vor der Umbenennung bleibt
; keine alte Exe und keine tote Verknüpfung zurück.
#if AppExe != AlteExe
Type: files; Name: "{app}\{#AlteExe}"
Type: files; Name: "{autoprograms}\{#AlterOrdner}.lnk"
Type: files; Name: "{autodesktop}\{#AlterOrdner}.lnk"
#endif

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[INI]
; Die App liest die Datei mit Rueckfall auf die ANSI-Codepage, falls Windows
; sie nicht in UTF-8 anlegt (Umlaute im Pfad).
Filename: "{localappdata}\{#Ordner}\einstellungen.ini"; Section: "Daten"; Key: "Ordner"; String: "{code:Datenordner}"
Filename: "{localappdata}\{#Ordner}\einstellungen.ini"; Section: "Daten"; Key: "OneDriveBestaetigt"; String: "{code:OneDriveBestaetigt}"

[Dirs]
; Der Datenordner gehoert dem Nutzer, nicht dem Installer: uninsneveruninstall.
Name: "{code:Datenordner}"; Flags: uninsneveruninstall

[Run]
#ifdef WebView2Bootstrapper
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Microsoft Edge WebView2 wird eingerichtet …"; Check: WebView2Fehlt
#endif
Filename: "{app}\{#AppExe}"; Description: "{#AppName} jetzt starten"; Flags: nowait postinstall skipifsilent
; NK-175: nach dem stillen Update aus der App startet sie wieder. Nur mit
; /NEUSTART=1, damit stille Installationen (Admin, CI-Probe) nichts starten.
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: NachUpdateStarten

[Code]
var
  DatenSeite: TInputDirWizardPage;
  OneDriveOk: Boolean;

function NachUpdateStarten: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:NEUSTART|0}') = '1');
end;

function WebView2Fehlt: Boolean;
var
  Version: String;
begin
  // Evergreen-Runtime (systemweit oder je Nutzer); Windows 11 bringt sie mit.
  Result := not (
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version))
    or (Version = '') or (Version = '0.0.0.0');
end;

function VorhandenerOrdner: String;
begin
  // Erst die eigene einstellungen.ini, dann die einer Installation vor der
  // Umbenennung (D-95), dann ein vorhandener alter Datenordner.
  Result := GetIniString('Daten', 'Ordner', '',
    ExpandConstant('{localappdata}\{#Ordner}\einstellungen.ini'));
  if Result = '' then
    Result := GetIniString('Daten', 'Ordner', '',
      ExpandConstant('{localappdata}\{#AlterOrdner}\einstellungen.ini'));
  if (Result = '') and FileExists(ExpandConstant('{userdocs}\{#AlterOrdner}\nebenkosten.db')) then
    Result := ExpandConstant('{userdocs}\{#AlterOrdner}');
end;

function LiegtInOneDrive(Pfad: String): Boolean;
var
  Namen: array[0..2] of String;
  I: Integer;
  Wurzel: String;
begin
  Result := False;
  Namen[0] := 'OneDrive';
  Namen[1] := 'OneDriveConsumer';
  Namen[2] := 'OneDriveCommercial';
  for I := 0 to 2 do
  begin
    Wurzel := RemoveBackslashUnlessRoot(GetEnv(Namen[I]));
    if (Wurzel <> '') and
       ((CompareText(Pfad, Wurzel) = 0) or
        (CompareText(Copy(Pfad, 1, Length(Wurzel) + 1), Wurzel + '\') = 0)) then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

procedure InitializeWizard;
var
  Vorgabe: String;
begin
  DatenSeite := CreateInputDirPage(wpSelectDir,
    'Wo sollen Ihre Daten liegen?',
    'Datenbank, Belege und Sicherungen liegen in einem eigenen Ordner.',
    '{#AppName} legt seine Daten in diesen Ordner. Er bleibt ' +
    'bei einem Update und bei der Deinstallation erhalten. Sichern Sie ihn ' +
    'regelmäßig (die App erinnert Sie daran).' + #13#10#13#10 +
    'Ordner:', False, '');
  DatenSeite.Add('');
  Vorgabe := VorhandenerOrdner;
  if Vorgabe = '' then
    Vorgabe := ExpandConstant('{userdocs}\{#Ordner}');
  DatenSeite.Values[0] := Vorgabe;
  OneDriveOk := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Lokal: String;
begin
  Result := True;
  if CurPageID <> DatenSeite.ID then
    Exit;
  if Pos(ExpandConstant('{app}'), DatenSeite.Values[0]) = 1 then
  begin
    MsgBox('Die Daten dürfen nicht im Programmordner liegen. Bitte wählen ' +
      'Sie einen anderen Ordner.', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  if LiegtInOneDrive(DatenSeite.Values[0]) then
  begin
    Lokal := ExpandConstant('{localappdata}\{#Ordner}\Daten');
    case MsgBox('Der gewählte Ordner liegt in OneDrive und würde in die Cloud ' +
        'synchronisiert. Das kann die Datenbank beschädigen, und die Daten ' +
        'Ihrer Mieter lägen bei Microsoft.' + #13#10#13#10 +
        'Sollen die Daten stattdessen lokal unter' + #13#10 + Lokal + #13#10 +
        'liegen? (Empfohlen. Sicherungen können Sie weiter nach „Dokumente“ legen.)',
        mbConfirmation, MB_YESNOCANCEL) of
      IDYES: DatenSeite.Values[0] := Lokal;
      IDNO: OneDriveOk := True;
    else
      Result := False;
    end;
  end;
end;

function Datenordner(Param: String): String;
begin
  Result := DatenSeite.Values[0];
end;

function OneDriveBestaetigt(Param: String): String;
begin
  if OneDriveOk then
    Result := '1'
  else
    Result := '0';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Ordner: String;
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
  begin
    Ordner := VorhandenerOrdner;
    if Ordner = '' then
      Ordner := ExpandConstant('{userdocs}\{#Ordner}');
    MsgBox('Das Programm ist entfernt. Ihre Daten (Datenbank, Belege, ' +
      'Sicherungen) bleiben erhalten in:' + #13#10#13#10 + Ordner + #13#10#13#10 +
      'Bei einer neuen Installation findet die App sie dort wieder. Wenn Sie ' +
      'sie nicht mehr brauchen, löschen Sie den Ordner selbst -- denken Sie ' +
      'an die Aufbewahrungsfristen.', mbInformation, MB_OK);
  end;
end;
