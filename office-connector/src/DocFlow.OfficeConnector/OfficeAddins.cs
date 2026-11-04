using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;

namespace DocFlow.OfficeConnector
{
    [ComImport, Guid("000C0396-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IRibbonExtensibility
    {
        [DispId(1)]
        [return: MarshalAs(UnmanagedType.BStr)]
        string GetCustomUI([MarshalAs(UnmanagedType.BStr)] string ribbonID);
    }

    // Office imports IDTExtensibility2 by its official COM IID. ComImport ensures
    // the managed COM Callable Wrapper exposes the real Office interface through QueryInterface.
    [ComImport, Guid("B65AD801-ABAF-11D0-BB8B-00A0C90F2744"), InterfaceType(ComInterfaceType.InterfaceIsDual), TypeLibType(TypeLibTypeFlags.FHidden | TypeLibTypeFlags.FDispatchable)]
    public interface IDTExtensibility2
    {
        [DispId(1)]
        void OnConnection([MarshalAs(UnmanagedType.IDispatch)] object application, ext_ConnectMode connectMode, [MarshalAs(UnmanagedType.IDispatch)] object addInInst, ref Array custom);
        [DispId(2)]
        void OnDisconnection(ext_DisconnectMode removeMode, ref Array custom);
        [DispId(3)]
        void OnAddInsUpdate(ref Array custom);
        [DispId(4)]
        void OnStartupComplete(ref Array custom);
        [DispId(5)]
        void OnBeginShutdown(ref Array custom);
    }
    [Guid("289E9AF1-4973-11D1-AE81-00A0C90F26F4")]
    public enum ext_ConnectMode { ext_cm_AfterStartup = 0, ext_cm_Startup = 1, ext_cm_External = 2, ext_cm_CommandLine = 3, ext_cm_Solution = 4, ext_cm_UISetup = 5 }
    [Guid("289E9AF2-4973-11D1-AE81-00A0C90F26F4")]
    public enum ext_DisconnectMode { ext_dm_HostShutdown = 0, ext_dm_UserClosed = 1, ext_dm_UISetupComplete = 2, ext_dm_SolutionClosed = 3 }

    // The default IDispatch must expose both Office lifecycle methods and Ribbon callbacks.
    // IDTExtensibility2 remains implemented separately with its official IID for Office QueryInterface.
    [Guid("A2B34E12-5E0B-4A76-9C83-7D0B2F5A6101"), InterfaceType(ComInterfaceType.InterfaceIsIDispatch)]
    public interface IDocFlowOfficeAddinDispatch
    {
        [DispId(1)] void OnConnection([MarshalAs(UnmanagedType.IDispatch)] object application, ext_ConnectMode connectMode, [MarshalAs(UnmanagedType.IDispatch)] object addInInst, ref Array custom);
        [DispId(2)] void OnDisconnection(ext_DisconnectMode removeMode, ref Array custom);
        [DispId(3)] void OnAddInsUpdate(ref Array custom);
        [DispId(4)] void OnStartupComplete(ref Array custom);
        [DispId(5)] void OnBeginShutdown(ref Array custom);
        [DispId(10)] void OnUpload([MarshalAs(UnmanagedType.IDispatch)] object control);
        [DispId(11)] void OnOpen([MarshalAs(UnmanagedType.IDispatch)] object control);
    }

    public abstract class OfficeAddinBase : IDTExtensibility2, IRibbonExtensibility, IDocFlowOfficeAddinDispatch
    {
        protected object ApplicationObject;
        protected abstract string HostName { get; }
        private static readonly object LogLock = new object();
        private static string LogPath
        {
            get { return System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DocFlow", "OfficeConnector.log"); }
        }
        protected static void Log(string message)
        {
            try
            {
                lock (LogLock)
                {
                    string path = LogPath;
                    System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path));
                    System.IO.File.AppendAllText(path, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + " [" + System.Threading.Thread.CurrentThread.ManagedThreadId + "] " + message + Environment.NewLine);
                }
            }
            catch { }
        }

        protected OfficeAddinBase() { Log("Constructor: " + GetType().FullName + " loaded."); }
        public void OnConnection(object application, ext_ConnectMode mode, object addInInst, ref Array custom)
        {
            Log(HostName + ": OnConnection entered; mode=" + mode);
            try { ApplicationObject = application; Log(HostName + ": OnConnection completed."); }
            catch (Exception ex) { Log(HostName + ": OnConnection ERROR: " + ex); }
        }
        public void OnDisconnection(ext_DisconnectMode mode, ref Array custom) { Log(HostName + ": OnDisconnection; mode=" + mode); ApplicationObject = null; }
        public void OnAddInsUpdate(ref Array custom) { Log(HostName + ": OnAddInsUpdate."); }
        public void OnStartupComplete(ref Array custom) { Log(HostName + ": OnStartupComplete."); }
        public void OnBeginShutdown(ref Array custom) { Log(HostName + ": OnBeginShutdown."); ApplicationObject = null; }

        public string GetCustomUI(string ribbonID)
        {
            Log(HostName + ": GetCustomUI; ribbonID=" + ribbonID);
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
                if (upload) SaveActiveDocument();
                // Resolve the path after Save: a new/unsaved Office document may
                // receive its real FullName only after the Save As dialog completes.
                string path = GetActiveFilePath();
                using (var form = new ConnectorForm(ApplicationObject, HostName, upload, path))
                    form.ShowDialog();
            }
            catch (Exception ex) { MessageBox.Show("DocFlow: " + ex.Message, "DocFlow", MessageBoxButtons.OK, MessageBoxIcon.Error); }
        }
        private string GetActiveFilePath()
        {
            dynamic app = ApplicationObject;
            dynamic doc = HostName == "Excel" ? app.ActiveWorkbook : app.ActiveDocument;
            try { return Convert.ToString(doc.FullName); } catch { return ""; }
        }
        private void SaveActiveDocument()
        {
            dynamic app = ApplicationObject;
            dynamic doc = HostName == "Excel" ? app.ActiveWorkbook : app.ActiveDocument;
            if (doc == null) throw new InvalidOperationException("Нет активного документа.");
            doc.Save();
        }
    }

    [ComVisible(true), Guid("B7D1C64C-84AE-4A67-9DB1-3B5C43E30101"), ProgId("DocFlow.WordAddin"), ClassInterface(ClassInterfaceType.None), ComDefaultInterface(typeof(IDocFlowOfficeAddinDispatch))]
    public class WordAddin : OfficeAddinBase { protected override string HostName { get { return "Word"; } } }
    [ComVisible(true), Guid("B7D1C64C-84AE-4A67-9DB1-3B5C43E30102"), ProgId("DocFlow.ExcelAddin"), ClassInterface(ClassInterfaceType.None), ComDefaultInterface(typeof(IDocFlowOfficeAddinDispatch))]
    public class ExcelAddin : OfficeAddinBase { protected override string HostName { get { return "Excel"; } } }
    [ComVisible(true), Guid("B7D1C64C-84AE-4A67-9DB1-3B5C43E30103"), ProgId("DocFlow.VisioAddin"), ClassInterface(ClassInterfaceType.None), ComDefaultInterface(typeof(IDocFlowOfficeAddinDispatch))]
    public class VisioAddin : OfficeAddinBase { protected override string HostName { get { return "Visio"; } } }
}
