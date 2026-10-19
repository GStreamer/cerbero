// Support code for Microsoft Windows ML license acceptance.

[Files]
Source: "{#WinMLLicenseFile}"; DestName: "winml-license.txt"; Flags: dontcopy noencryption;

[CustomMessages]
WizardWinMLLicense=Microsoft Windows ML License Agreement
WinMLLicenseLabel=Please read the license agreement before installing the Windows ML components.
WinMLLicenseLabel3=These terms apply to the Microsoft Windows ML components you selected.

[Code]
const
  winml_accept_param = '/WinMLLicenseAccepted=';
var
  winml_license_page: TOutputMsgMemoWizardPage;
  winml_license_accept: TRadioButton;
  winml_license_reject: TRadioButton;

function gst_winml_selected: Boolean;
begin
  Result := WizardIsComponentSelected('gstreamer_1_0_analytics_winml/runtime') or
    WizardIsComponentSelected('gstreamer_1_0_analytics_winml/devel') or
    WizardIsComponentSelected('gstreamer_1_0_analytics_winml/debug');
end;

function gst_winml_command_line_accepted: Boolean;
begin
  Result := ExpandConstant('{param:WinMLLicenseAccepted|0}') = '1';
end;

function gst_winml_license_accepted: Boolean;
begin
  Result := gst_winml_command_line_accepted;
  if not WizardSilent then
    Result := Result or winml_license_accept.Checked;
end;

procedure gst_winml_license_accept(sender: TObject);
begin
  if WizardForm.CurPageID = winml_license_page.ID then
    WizardForm.NextButton.Enabled := winml_license_accept.Checked;
end;

<event('InitializeWizard')>
procedure gst_winml_initialize_wizard;
var
  license_path: String;
begin
  winml_license_page := CreateOutputMsgMemoPage(wpSelectComponents, ExpandConstant('{cm:WizardWinMLLicense}'),
    ExpandConstant('{cm:WinMLLicenseLabel}'), ExpandConstant('{cm:WinMLLicenseLabel3}'), '');

  ExtractTemporaryFile('winml-license.txt');
  license_path := ExpandConstant('{tmp}\winml-license.txt');
  winml_license_page.RichEditViewer.UseRichEdit := False;
  winml_license_page.RichEditViewer.Lines.LoadFromFile(license_path);
  DeleteFile(license_path);
  winml_license_page.RichEditViewer.Width := winml_license_page.SurfaceWidth;

  winml_license_accept := TRadioButton.Create(winml_license_page);
  winml_license_accept.Parent := winml_license_page.Surface;
  winml_license_accept.Caption := WizardForm.LicenseAcceptedRadio.Caption;
  winml_license_accept.Left := WizardForm.LicenseAcceptedRadio.Left;
  winml_license_accept.Top := WizardForm.LicenseAcceptedRadio.Top;
  winml_license_accept.Width := WizardForm.LicenseAcceptedRadio.Width;
  winml_license_accept.Height := WizardForm.LicenseAcceptedRadio.Height;
  winml_license_accept.Anchors := WizardForm.LicenseAcceptedRadio.Anchors;
  winml_license_accept.OnClick := @gst_winml_license_accept;
  
  winml_license_reject := TRadioButton.Create(winml_license_page);
  winml_license_reject.Parent := winml_license_page.Surface;
  winml_license_reject.Caption := WizardForm.LicenseNotAcceptedRadio.Caption;
  winml_license_reject.Left := WizardForm.LicenseNotAcceptedRadio.Left;
  winml_license_reject.Top := WizardForm.LicenseNotAcceptedRadio.Top;
  winml_license_reject.Width := WizardForm.LicenseNotAcceptedRadio.Width;
  winml_license_reject.Height := WizardForm.LicenseNotAcceptedRadio.Height;
  winml_license_reject.Anchors := WizardForm.LicenseNotAcceptedRadio.Anchors;
  winml_license_reject.OnClick := @gst_winml_license_accept;

  // Measure these by hand if it needs adjustment
  winml_license_page.RichEditViewer.Height := winml_license_page.SurfaceHeight - winml_license_reject.Height - winml_license_accept.Height - ScaleY(44);

  winml_license_accept.Checked := gst_winml_command_line_accepted;
  winml_license_reject.Checked := not gst_winml_command_line_accepted;
end;

<event('CurPageChanged')>
procedure gst_winml_cur_page_changed(CurPageID: Integer);
begin
  if CurPageID = winml_license_page.ID then begin
    WizardForm.NextButton.Enabled := winml_license_accept.Checked;
  end;
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
