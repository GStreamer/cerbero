function OnFinish(selProj, selObj)
{
	try
	{
		var strProjectPath = wizard.FindSymbol('PROJECT_PATH');
		var strProjectName = wizard.FindSymbol('PROJECT_NAME');

		selProj = CreateCustomProject(strProjectName, strProjectPath);
		AddFilters(selProj);

		selProj.Object.Save();
	}
	catch(e)
	{
		if (e.description.length != 0)
			SetErrorInfo(e);
		return e.number
	}
}

function CreateCustomProject(strProjectName, strProjectPath)
{
	try
	{
		var strProjTemplatePath = wizard.FindSymbol('PROJECT_TEMPLATE_PATH');
		var strProjTemplate = strProjTemplatePath + '\\gst-sdk-template\\gst-template.vcxproj';

		var Solution = dte.Solution;
		var strSolutionName = "";
		if (wizard.FindSymbol("CLOSE_SOLUTION"))
		{
			Solution.Close();
			strSolutionName = wizard.FindSymbol("VS_SOLUTION_NAME");
			if (strSolutionName.length)
			{
				var strSolutionPath = strProjectPath.substr(0, strProjectPath.length - strProjectName.length);
				Solution.Create(strSolutionPath, strSolutionName);
			}
		}

		var strProjectNameWithExt = strProjectName + '.vcxproj';

		var oTarget = wizard.FindSymbol("TARGET");
		var prj;
		if (wizard.FindSymbol("WIZARD_TYPE") == vsWizardAddSubProject)  // vsWizardAddSubProject
		{
			var prjItem = oTarget.AddFromTemplate(strProjTemplate, strProjectNameWithExt);
			prj = prjItem.SubProject;
		}
		else
		{
			prj = oTarget.AddFromTemplate(strProjTemplate, strProjectPath, strProjectNameWithExt);
		}
		return prj;
	}
	catch(e)
	{
		throw e;
	}
}

function AddFilters(proj)
{
	try
	{
		var group = proj.Object.AddFilter('Source Files');
		group.Filter = "cpp;c;cc;cxx;c++;cppm;ixx;def;odl;idl;hpj;bat;asm;asmx";
		group.UniqueIdentifier = "{4FC737F1-C7A5-4376-A066-2A32D752A2FF}";
		group = proj.Object.AddFilter('Header Files');
		group.Filter = "h;hh;hpp;hxx;h++;hm;inl;inc;ipp;xsd";
		group.UniqueIdentifier = "{93995380-89BD-4b04-88EB-625FBE52EBFB}";
		group = proj.Object.AddFilter('Resource Files');
		group.Filter = "rc;ico;cur;bmp;dlg;rc2;rct;bin;rgs;gif;jpg;jpeg;jpe;resx;tiff;tif;png;wav;mfcribbon-ms";
		group.UniqueIdentifier = "{67DA6AB6-F800-4c08-8B7A-83BB121AAD01}";
	}
	catch(e)
	{
		throw e;
	}
}


function GetTargetName(strName, strProjectName)
{
	try
	{
		// TODO: set the name of the rendered file based on the template filename
		var strTarget = strName;

		if (strName == 'readme.txt')
			strTarget = 'ReadMe.txt';

		if (strName == 'sample.txt')
			strTarget = 'Sample.txt';

		return strTarget;
	}
	catch(e)
	{
		throw e;
	}
}
