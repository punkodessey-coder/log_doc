using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;

namespace DocFlow.OfficeConnector
{
    [ComImport, Guid("000C0396-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IRibbonExtensibility { [return: MarshalAs(UnmanagedType.BStr)] string GetCustomUI([MarshalAs(UnmanagedType.BStr)] string ribbonID); }

    [ComImport, Guid("B65AD801-ABAF-11D0-BB8B-00A0C90F2744"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IDTExtensibility2
    {
        void OnConnection([MarshalAs(UnmanagedType.IDispatch)] object application, ext_ConnectMode connectMode, [MarshalAs(UnmanagedType.IDispatch)] object addInInst, ref Array custom);
        void OnDisconnection(ext_DisconnectMode removeMode, ref Array custom);
        void OnAddInsUpdate(ref Array custom);
        void OnStartupComplete(ref Array custom);
        void OnBeginShutdown(ref Array custom);
    }
    public enum ext_ConnectMode { ext_cm_AfterStartup = 0, ext_cm_Startup = 1, ext_cm_External = 2, ext_cm_CommandLine = 3, ext_cm_ solution = 4, ext_cm_UISetup = 5 }
    public enum ext_DisconnectMode { ext_dm_HostShutdown = 0, ext_dm_UserClosed = 1, ext_dm_ solutionClosed = 2, ext_dm_UISetupComplete = 3 }

    public abstract class OfficeAddinBase : IDTExtensibility2, IRibbonExtensibility
    {
        protected object ApplicationObject;
        protected abstract string HostName { get; }
        public void OnConnection(object application, ext_ConnectMode mode, object addInInst, ref Array custom) { ApplicationObject = application; }
        public void OnDisconnection(ext_DisconnectMode mode, ref Array custom) { ApplicationObject = null; }
        public void OnAddInsUpdate(ref Array custom) { }
        public void OnStartupComplete(ref Array custom) { }
        public void OnBeginShutdown(ref Array custom) { ApplicationObject = null; }

        public string GetCustomUI(string ribbonID)
        {
            return @"<customUI xmlns=""http://schemas.microsoft.com/office/2009/07/customui"">
              <ribbon><tabs><tab id=""DocFlowTab"" label=""DocFlow"">
                <group id=""DocFlowGroup"" label=""Хранилище документов"">
                  <button id=""UploadButton"" label=""Отправить в хранилище"" size=""large"" onAction=""OnUpload"" imageMso=""FileSave""/>
                  <button id=""OpenButton"" label=""Открыть из хранилища"" size=""large"" onAction=""OnOpen"" imageMso=""FileOpen""/>
                </group>
              </tab></tabs></ribbon></customUI>";
        }
        public void OnUpload(object control) { RunDialog(true); }
        public void OnOpen(object control) { RunDialog(false); }
        private void RunDialog(bool upload)
        {
            if (ApplicationObject == null) return;
            try
            {
                string path = GetActiveFilePath();
                if (upload && !String.IsNullOrWhiteSpace(path)) SaveActiveDocument();
                using (var form = new ConnectorForm(ApplicationObject, HostName, upload, path))
                    form.ShowDialog();
            }
            catch (Exception ex) { MessageBox.Show("DocFlow: " + ex.Message, "DocFlow", MessageBoxButtons.OK, MessageBoxIcon.Error); }
        }
        private string GetActiveFilePath()
        {
            dynamic app = ApplicationObject;
            dynamic doc = app.ActiveDocument;
            try { return Convert.ToString(doc.FullName); } catch { return ""; }
        }
        private void SaveActiveDocument()
        {
            dynamic app = ApplicationObject;
            dynamic doc = app.ActiveDocument;
            doc.Save();
        }
    }

    [ComVisible(true), Guid("B7D1C64C-84AE-4A67-9DB1-3B5C43E30101"), ProgId("DocFlow.WordAddin"), ClassInterface(ClassInterfaceType.None)]
    public class WordAddin : OfficeAddinBase { protected override string HostName { get { return "Word"; } } }
    [ComVisible(true), Guid("B7D1C64C-84AE-4A67-9DB1-3B5C43E30102"), ProgId("DocFlow.ExcelAddin"), ClassInterface(ClassInterfaceType.None)]
    public class ExcelAddin : OfficeAddinBase { protected override string HostName { get { return "Excel"; } } }
    [ComVisible(true), Guid("B7D1C64C-84AE-4A67-9DB1-3B5C43E30103"), ProgId("DocFlow.VisioAddin"), ClassInterface(ClassInterfaceType.None)]
    public class VisioAddin : OfficeAddinBase { protected override string HostName { get { return "Visio"; } } }
}