;
; ImageTo3D Pro v2.1.0 - Inno Setup Script
; Professional Windows Installer
;

#define MyAppName "ImageTo3D Pro"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "ImageTo3D Pro"
#define MyAppExeName "ImageTo3DPro.exe"
#define MyAppAssocName MyAppName + " File"
#define MyAppAssocExt ".myp"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
; Application Information
AppId={{ImageTo3DPro-v2.1.0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=no
ChangesAssociations=yes
DisableWelcomePage=no

; Compression and Output
Compression=lzma2/ultra
SolidCompression=yes
LZMAAlgorithm=1
LZMABlockSize=262144
LZMANumBlockThreads=4
LZMANumFastBytes=273
OutputDir=output
OutputBaseFilename=ImageTo3DPro_Setup_v{#MyAppVersion}
SetupIconFile=setup_assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

; Installation Behavior
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x86 x64
ArchitecturesInstallIn64BitMode=x64

; User Interface
WizardStyle=modern
WizardImageFile=setup_assets\wizard.bmp
WizardSmallImageFile=setup_assets\logo.bmp
WizardImageStretch=no
WizardSizePercent=100

; Version Info
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Image to 3D Model Converter
VersionInfoTextVersion={#MyAppVersion}
VersionInfoCopyright=Copyright (c) 2024
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

; Windows Version Support
MinVersion=6.1.7600
OnlyBelowVersion=0

; Other Settings
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
ShowLanguageDialog=no
LanguageDetectionMethod=none

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Full Installation"
Name: "compact"; Description: "Compact Installation"
Name: "custom"; Description: "Custom Installation"; Flags: iscustom

[Components]
Name: "main"; Description: "Main Application"; Types: full compact custom; Flags: fixed
Name: "samples"; Description: "Sample Images"; Types: full custom
Name: "docs"; Description: "Documentation"; Types: full custom

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Components: main
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Main Application
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Components: main; Flags: ignoreversion

; Sample Images
Source: "include\sample_images\*"; DestDir: "{app}\Samples"; Components: samples; Flags: ignoreversion recursesubdirs createallsubdirs

; Documentation
Source: "include\docs\*"; DestDir: "{app}\Docs"; Components: docs; Flags: ignoreversion recursesubdirs createallsubdirs

; Styles and Configs
Source: "..\ui\desktop\styles.qss"; DestDir: "{app}"; Components: main; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{group}\Documentation"; Filename: "{app}\Docs\README.md"; Components: docs
Name: "{group}\User Guide"; Filename: "{app}\Docs\06_USER_GUIDE.md"; Components: docs

; Desktop (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

; Quick Launch (optional)
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
; Launch application checkbox on finish page
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent unchecked

[Registry]
; Uninstall registry entries
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"

; Application registry key (for version checking)
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\*"

[Code]
var
  UpgradePage: TOutputMsgWizardPage;
  OldVersion: string;
  OldPath: string;

// Check if previous version exists
function InitializeSetup(): Boolean;
var
  Version: String;
begin
  Result := True;
  
  // Check registry for previous installation
  if RegQueryStringValue(HKLM, 'SOFTWARE\{#MyAppPublisher}\{#MyAppName}', 'Version', Version) then
  begin
    OldVersion := Version;
    if RegQueryStringValue(HKLM, 'SOFTWARE\{#MyAppPublisher}\{#MyAppName}', 'InstallPath', OldPath) then
    begin
      if Version < '{#MyAppVersion}' then
      begin
        // Previous version found, will show upgrade page
        Log('Previous version ' + Version + ' found at ' + OldPath);
      end;
    end;
  end;
end;

// Create upgrade notification page
procedure InitializeWizard();
begin
  if OldVersion <> '' then
  begin
    UpgradePage := CreateOutputMsgPage(wpWelcome,
      'Upgrade Installation',
      'Setup has detected a previous version of ImageTo3D Pro.',
      'Setup has detected ImageTo3D Pro version ' + OldVersion + ' installed on your system.' + #13#10 + #13#10 +
      'This wizard will upgrade your installation to version {#MyAppVersion}.' + #13#10 +
      'Your existing settings and data will be preserved.' + #13#10 + #13#10 +
      'Click Next to continue with the upgrade.'
    );
  end;
end;

// Custom welcome page text
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
  begin
    if OldVersion <> '' then
    begin
      WizardForm.WelcomeLabel1.Caption := 'Welcome to the ImageTo3D Pro v{#MyAppVersion} Upgrade Wizard';
      WizardForm.WelcomeLabel2.Caption := 'This wizard will upgrade your existing installation from version ' + OldVersion + ' to version {#MyAppVersion}.' + #13#10 + #13#10 +
        'It is recommended that you close all other applications before continuing.' + #13#10 + #13#10 +
        'Click Next to continue, or Cancel to exit Setup.';
    end else
    begin
      WizardForm.WelcomeLabel1.Caption := 'Welcome to the ImageTo3D Pro v{#MyAppVersion} Setup Wizard';
      WizardForm.WelcomeLabel2.Caption := 'This wizard will install ImageTo3D Pro v{#MyAppVersion} on your computer.' + #13#10 + #13#10 +
        'ImageTo3D Pro converts 2D images into 3D models using AI-powered algorithms.' + #13#10 + #13#10 +
        'It is recommended that you close all other applications before continuing.' + #13#10 + #13#10 +
        'Click Next to continue, or Cancel to exit Setup.';
    end;
  end;
end;

// Check if we need to uninstall previous version
function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
  UninstallString: String;
begin
  Result := True;
  
  if (CurPageID = wpWelcome) and (OldVersion <> '') then
  begin
    // Check if there's an uninstaller
    if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1', 'UninstallString', UninstallString) then
    begin
      // Run uninstaller silently
      if Exec(RemoveQuotes(UninstallString), '/SILENT /NORESTART', '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode) then
      begin
        Log('Uninstalled previous version with result code: ' + IntToStr(ResultCode));
      end;
    end;
  end;
end;

// Custom license page (no actual license, just informational)
procedure CurPageIDChanged(CurPageID: Integer);
begin
  if CurPageID = wpLicense then
  begin
    // No license required - just informational text
    WizardForm.LicenseMemo.Text := 
      'ImageTo3D Pro v{#MyAppVersion}' + #13#10 + #13#10 +
      'This software is provided as-is without any warranty.' + #13#10 + #13#10 +
      'By installing this software, you agree to use it responsibly.' + #13#10 + #13#10 +
      'For support and documentation, please visit the application folder.' + #13#10 +
      'Documentation is available in the Docs folder after installation.';
  end;
end;

// Initialize installation
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  NeedsRestart := False;
end;

// Check Windows version compatibility
function InitializeWizardCheck(): Boolean;
var
  Version: TWindowsVersion;
begin
  Result := True;
  GetWindowsVersionEx(Version);
  
  // Check for Windows 7 or higher
  if Version.Major < 6 then
  begin
    MsgBox('ImageTo3D Pro requires Windows 7 or higher.', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  
  // Warn about Windows 7/8 (not officially supported but may work)
  if (Version.Major = 6) and (Version.Minor < 2) then
  begin
    if MsgBox('Warning: ImageTo3D Pro is optimized for Windows 10 and 11. ' +
              'Installation on Windows 7 or 8 may not work correctly.' + #13#10 + #13#10 +
              'Do you want to continue anyway?', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

// Post-installation tasks
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Log installation success
    Log('ImageTo3D Pro v{#MyAppVersion} installed successfully to ' + ExpandConstant('{app}'));
  end;
end;
