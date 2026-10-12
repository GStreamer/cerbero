// Support code for Microsoft Windows ML license acceptance.

[Files]
Source: "{#WinMLLicenseFile}"; DestName: "winml-license.txt"; Flags: dontcopy noencryption;

[Code]
const
  winml_accept_param = '/WinMLLicenseAccepted=';
var
  winml_license_page: TOutputMsgMemoWizardPage;
  winml_license_accept: TNewCheckBox;

function gst_winml_selected: Boolean;
begin
  Result := WizardIsComponentSelected('gstreamer_1_0_analytics_winml/runtime') or
    WizardIsComponentSelected('gstreamer_1_0_analytics_winml/devel') or
    WizardIsComponentSelected('gstreamer_1_0_analytics_winml/debug');
end;

function gst_winml_command_line_accepted: Boolean;
var
  i: Integer;
  param: String;
begin
  Result := False;
  for i := 1 to ParamCount do begin
    param := ParamStr(i);
    if CompareText(Copy(param, 1, Length(winml_accept_param)), winml_accept_param) = 0 then
      Result := Copy(param, Length(winml_accept_param) + 1, MaxInt) = '1';
  end;
end;

function gst_winml_license_accepted: Boolean;
begin
  Result := gst_winml_command_line_accepted;
  if not WizardSilent then
    Result := Result or winml_license_accept.Checked;
end;

<event('InitializeWizard')>
procedure gst_winml_initialize_wizard;
var
  license_text: AnsiString;
begin
  winml_license_page := CreateOutputMsgMemoPage(wpSelectComponents,
    'Microsoft Windows ML License Agreement',
    'Please read the license agreement before installing the Windows ML components.',
    'These terms apply to the Microsoft Windows ML components you selected.', '');
  ExtractTemporaryFile('winml-license.txt');
  if not LoadStringFromFile(ExpandConstant('{tmp}\winml-license.txt'), license_text) then
    RaiseException('Could not load the Microsoft Windows ML license agreement.');
  winml_license_page.RichEditViewer.RTFText := license_text;
  winml_license_page.RichEditViewer.Height :=
    winml_license_page.RichEditViewer.Height - ScaleY(36);
  winml_license_accept := TNewCheckBox.Create(winml_license_page);
  winml_license_accept.Parent := winml_license_page.Surface;
  winml_license_accept.Left := 0;
  winml_license_accept.Top := winml_license_page.SurfaceHeight - ScaleY(28);
  winml_license_accept.Width := winml_license_page.SurfaceWidth;
  winml_license_accept.Height := ScaleY(24);
  winml_license_accept.Anchors := [akLeft, akRight, akBottom];
  winml_license_accept.Caption := 'I accept the Microsoft Windows ML license agreement';
end;

<event('ShouldSkipPage')>
function gst_winml_should_skip_page(PageID: Integer): Boolean;
begin
  Result := (PageID = winml_license_page.ID) and
    (not gst_winml_selected or gst_winml_command_line_accepted or WizardSilent);
end;

<event('NextButtonClick')>
function gst_winml_next_button_click(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = winml_license_page.ID) and gst_winml_selected and
      not gst_winml_license_accepted then begin
    MsgBox('You must accept the Microsoft Windows ML license agreement to install these components.',
      mbError, MB_OK);
    Result := False;
  end;
end;

<event('PrepareToInstall')>
function gst_winml_prepare_to_install(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if gst_winml_selected then begin
    if not gst_winml_license_accepted then begin
      Result := 'Microsoft Windows ML license acceptance is required. ' +
        'For silent installation, specify /WinMLLicenseAccepted=1 or exclude the Windows ML components.';
      Log(Result);
    end else
      Log('Microsoft Windows ML license accepted for this installation.');
  end;
end;
