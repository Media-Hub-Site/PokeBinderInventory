; Script de Inno Setup para PokeBinder (Media Hub)
#define MyAppName "PokeBinder"
#define MyAppVersion "1.5.0"
#define MyAppPublisher "Media Hub (Alan Dave)"
#define MyAppURL "https://github.com/Media-Hub-Site/PokeBinderInventory"
#define MyAppExeName "PokeBinder.exe"

[Setup]
AppId={{C82F5BA2-4703-49D8-B71E-DB93B8F06F63}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableDirPage=no
UsePreviousAppDir=yes
AppendDefaultDirName=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=PokeBinder-Setup
SetupIconFile=assets\icons\TCG_Logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "downloadimages"; Description: "Descargar paquete de imágenes de cartas Pokémon TCG (~250 MB)"; GroupDescription: "Recursos adicionales:"; Flags: checkedonce

[Files]
Source: "dist\PokeBinder\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Otorgar permisos de escritura para el caché de imágenes locales en {app}\assets
Name: "{app}"; Permissions: users-modify
Name: "{app}\assets"; Permissions: users-modify
Name: "{app}\assets\images"; Permissions: users-modify
Name: "{app}\assets\images_hd"; Permissions: users-modify
Name: "{app}\assets\images_webp"; Permissions: users-modify

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Instalando Microsoft Visual C++ Redistributable (x64)..."; Flags: waituntilterminated; Check: ShouldInstallVCRedist
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
var
  DownloadPage: TDownloadWizardPage;
  NeedsVCRedist: Boolean;
  NeedsImages: Boolean;

function IsVCRedistInstalled(): Boolean;
var
  Installed: Cardinal;
begin
  Result := False;
  if RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) then
  begin
    if Installed = 1 then
    begin
      Result := True;
      Exit;
    end;
  end;
  if RegQueryDWordValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) then
  begin
    if Installed = 1 then
      Result := True;
  end;
end;

function ShouldInstallVCRedist(): Boolean;
begin
  Result := NeedsVCRedist and FileExists(ExpandConstant('{tmp}\vc_redist.x64.exe'));
end;

procedure InitializeWizard;
begin
  NeedsVCRedist := False;
  NeedsImages := False;
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then
  begin
    NeedsVCRedist := not IsVCRedistInstalled();
    NeedsImages := WizardIsTaskSelected('downloadimages');

    if NeedsVCRedist or NeedsImages then
    begin
      DownloadPage.Clear;
      if NeedsVCRedist then
        DownloadPage.Add('https://aka.ms/vs/17/release/vc_redist.x64.exe', 'vc_redist.x64.exe', '');
      if NeedsImages then
        DownloadPage.Add('https://github.com/Media-Hub-Site/PokeBinderInventory/releases/download/assets-v1/images.zip', 'images.zip', '');

      DownloadPage.Show;
      try
        try
          DownloadPage.Download;
        except
          if DownloadPage.AbortedByUser then
          begin
            Log('Descarga cancelada por el usuario.');
            Result := False;
          end
          else
          begin
            SuppressibleMsgBox(
              'Ocurrió un error al descargar los recursos adicionales:' + #13#10 +
              GetExceptionMessage + #13#10#13#10 +
              'La instalación continuará con los archivos descargados correctamente.',
              mbError, MB_OK, IDOK);
            if not FileExists(ExpandConstant('{tmp}\vc_redist.x64.exe')) then
              NeedsVCRedist := False;
            if not FileExists(ExpandConstant('{tmp}\images.zip')) then
              NeedsImages := False;
          end;
        end;
      finally
        DownloadPage.Hide;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  ZipPath: String;
  ExtractDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    ZipPath := ExpandConstant('{tmp}\images.zip');
    if NeedsImages and FileExists(ZipPath) then
    begin
      ExtractDir := ExpandConstant('{app}\assets');
      ForceDirectories(ExtractDir);

      WizardForm.StatusLabel.Caption := 'Descomprimiendo paquete de imágenes de cartas Pokémon TCG...';
      WizardForm.ProgressGauge.Style := npbstMarquee;

      // Usar tar.exe nativo de Windows 10/11 (mucho más rápido con miles de archivos)
      if not Exec('tar.exe', '-xf "' + ZipPath + '" -C "' + ExtractDir + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      begin
        // Respaldo con PowerShell Expand-Archive si tar.exe no estuviera disponible
        Exec('powershell.exe',
             '-NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath ''' + ZipPath + ''' -DestinationPath ''' + ExtractDir + ''' -Force"',
             '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      end;

      if ResultCode <> 0 then
      begin
        SuppressibleMsgBox(
          'No se pudo descomprimir el paquete de imágenes de cartas. Puedes volver a ejecutar el instalador más tarde o descargar las imágenes desde la aplicación.',
          mbError, MB_OK, IDOK);
      end;
    end;
  end;
end;
