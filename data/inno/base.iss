// Support code for Visual Studio installers detection.

[Code]
var
  gst_vs_found: Boolean;
  gst_vswhere_found: Boolean;
  vswhere_path: String;
  vs2017_path: String;
  vs2019_path: String;
  vs2022_path: String;
  vs2026_path: String;
const
  vsargs = '-prerelease -utf8 -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property resolvedInstallationPath -format value';

function gst_vs_find_vswhere(): String;
var
  vswhere: String;
begin
  if not gst_vswhere_found then begin
    vswhere := ExpandConstant('{commonpf32}\Microsoft Visual Studio\Installer\vswhere.exe');
    if FileExists(vswhere) then
      vswhere_path := vswhere;
    gst_vswhere_found := True;
  end;
  Result := vswhere_path;
end;

function gst_vs_find_install(range: String): String;
var
  vswhere: String;
  args: String;
  success: Boolean;
  result_code: Integer;
  output: TExecOutput;
begin
  vswhere := gst_vs_find_vswhere();
  if vswhere <> '' then begin
    try
      args := vsargs + ' -version ' + range;
	    Log('Querying ' + range  + ' ' + vswhere + ' ' + args); //, mbError, MB_OK);
      success := ExecAndCaptureOutput(vswhere, args, '', SW_SHOWNORMAL, ewWaitUntilTerminated, result_code, output);
    except
      Log('Unable to detect Visual Studio installations: ' + AddPeriod(GetExceptionMessage)); //, mbError, MB_OK);
    end
  end;
  if success then begin
    Log('Found Visual Studio installation: ' + range  + ' ' + output.StdOut[0]); //, mbError, MB_OK);
    Result := output.StdOut[0]
  end;
end;

function gst_vs_find_installations(): Boolean;
begin
  if not gst_vs_found then begin
    Log('Running VS install checks');
    gst_vs_found := True;
    vs2017_path := gst_vs_find_install('[15.0,16.0)');
    vs2019_path := gst_vs_find_install('[16.0,17.0)');
    vs2022_path := gst_vs_find_install('[17.0,18.0)');
    vs2026_path := gst_vs_find_install('[18.0,19.0)');
  end;
  Result := gst_vs_found;
end;

function gst_vs_install_dir(version: String): String;
begin
  if version = '2017' then
    Result := vs2017_path
  else if version = '2019' then
    Result := vs2019_path
  else if version = '2022' then
    Result := vs2022_path
  else if version = '2026' then
    Result := vs2026_path;
end;

function gst_vs_wizard_folder(Param: String): String;
begin
  Result := gst_vs_install_dir(Param) + '\Common7\Ide\VCProjects';
end;

function gst_vs_templates_folder(Param: String): String;
begin
  Result := gst_vs_install_dir(Param) + '\Common7\Ide\VCWizards';
end;

function gst_is_vs_version_installed(Param: String): Boolean;
begin
  if not gst_vs_found then begin
    gst_vs_find_installations();
  end;
  Result := gst_vs_install_dir(Param) <> '';
end;

procedure gst_test_unset_vs(Param: String);
begin
  if not gst_is_vs_version_installed(Param) then begin
    Log('VS ' + Param + ' not found, unchecking');
    WizardSelectComponents('!gstreamer_1_0_vs_templates_' + Param + '_devel');
  end;
end;

procedure InitializeWizard();
begin
  if gst_vs_find_installations() then
  begin
	  Log('Visual Studio checks completed, updating checks');
    gst_test_unset_vs('2017');
    gst_test_unset_vs('2019');
    gst_test_unset_vs('2022');
    gst_test_unset_vs('2026');
  end;
end;

procedure gst_register_vs_templates(Param: String);
var
  devenv: String;
  result_code: Integer;
begin
  devenv := gst_vs_install_dir(Param) + '\Common7\IDE\devenv.exe';
  if FileExists(devenv) then begin
    ExecAndLogOutput(devenv, '/InstallVSTemplates', '', SW_SHOWNORMAL, ewWaitUntilTerminated, result_code, nil);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('register_templates') then
  begin
    if WizardIsTaskSelected('gstreamer_1_0_vs_templates_2017_devel') then
      gst_register_vs_templates('2017');
    if WizardIsTaskSelected('gstreamer_1_0_vs_templates_2019_devel') then
      gst_register_vs_templates('2019');
    if WizardIsTaskSelected('gstreamer_1_0_vs_templates_2022_devel') then
      gst_register_vs_templates('2022');
    if WizardIsTaskSelected('gstreamer_1_0_vs_templates_2026_devel') then
      gst_register_vs_templates('2026');
  end;
end;

