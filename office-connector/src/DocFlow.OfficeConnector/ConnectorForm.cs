using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace DocFlow.OfficeConnector
{
    public sealed class ConnectorForm : Form
    {
        private readonly object officeApp;
        private readonly string host, activePath;
        private readonly bool uploadMode;
        private TextBox server, username, password, comment;
        private ComboBox projects, branches, folders, documents, versions;
        private Button action, refresh;
        private Label status;
        private DocFlowClient client;
        private List<ApiItem> projectItems = new List<ApiItem>(), branchItems = new List<ApiItem>(), folderItems = new List<ApiItem>(), documentItems = new List<ApiItem>(), versionItems = new List<ApiItem>();

        public ConnectorForm(object app, string hostName, bool upload, string path)
        {
            officeApp = app; host = hostName; uploadMode = upload; activePath = path;
            Text = upload ? "Отправить в DocFlow" : "Открыть из DocFlow";
            Width = 560; Height = 590; StartPosition = FormStartPosition.CenterScreen; MinimizeBox = false; MaximizeBox = false;
            BuildUi();
        }
        private void BuildUi()
        {
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(14), ColumnCount = 2, RowCount = 10 };
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 125)); layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            Controls.Add(layout);
            server = AddText(layout, "Адрес сервера", "http://127.0.0.1:8000");
            username = AddText(layout, "Логин", "");
            password = AddText(layout, "Пароль", ""); password.UseSystemPasswordChar = true;
            projects = AddCombo(layout, "Проект"); branches = AddCombo(layout, "Ветка"); folders = AddCombo(layout, "Папка");
            documents = AddCombo(layout, "Документ"); versions = AddCombo(layout, "Версия");
            comment = AddText(layout, "Комментарий", uploadMode ? "Обновление из " + host : "");
            status = new Label { AutoSize = true, ForeColor = System.Drawing.Color.DimGray, Text = activePath, Dock = DockStyle.Fill };
            layout.Controls.Add(new Label { Text = "Локальный файл", AutoSize = true, Anchor = AnchorStyles.Left }, 0, layout.RowCount++);
            layout.Controls.Add(status, 1, layout.RowCount - 1);
            var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft };
            action = new Button { Text = uploadMode ? "Отправить" : "Скачать и открыть", Width = 145, Height = 32 };
            refresh = new Button { Text = "Обновить списки", Width = 125, Height = 32 };
            buttons.Controls.Add(action); buttons.Controls.Add(refresh);
            layout.Controls.Add(buttons, 1, layout.RowCount++);
            action.Click += async (s,e) => await ExecuteAction();
            refresh.Click += async (s,e) => await ConnectAndLoad();
            projects.SelectedIndexChanged += async (s,e) => await LoadProject();
            branches.SelectedIndexChanged += async (s,e) => await LoadDocuments();
            folders.SelectedIndexChanged += async (s,e) => await LoadDocuments();
            documents.SelectedIndexChanged += async (s,e) => await LoadVersions();
            Shown += async (s,e) => await ConnectAndLoad();
        }
        private TextBox AddText(TableLayoutPanel p, string label, string value)
        {
            int row = p.RowCount++; p.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
            p.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left }, 0, row);
            var box = new TextBox { Text = value, Dock = DockStyle.Fill };
            p.Controls.Add(box, 1, row); return box;
        }
        private ComboBox AddCombo(TableLayoutPanel p, string label)
        {
            int row = p.RowCount++; p.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
            p.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left }, 0, row);
            var box = new ComboBox { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
            p.Controls.Add(box, 1, row); return box;
        }
        private void SetStatus(string text) { status.Text = text; }
        private async Task ConnectAndLoad()
        {
            try
            {
                UseWaitCursor = true; SetStatus("Подключение к DocFlow...");
                if (client != null) client.Dispose();
                client = new DocFlowClient(server.Text);
                await client.Login(username.Text, password.Text);
                projectItems = await client.Projects(); projects.DataSource = projectItems; projects.DisplayMember = "Name";
                SetStatus("Подключено. Выберите проект, ветку и папку.");
                if (projectItems.Count > 0) await LoadProject();
            }
            catch (Exception ex) { SetStatus("Ошибка: " + ex.Message); }
            finally { UseWaitCursor = false; }
        }
        private async Task LoadProject()
        {
            var p = projects.SelectedItem as ApiItem; if (p == null || client == null) return;
            try
            {
                UseWaitCursor = true;
                branchItems = await client.Branches(p.Id); branches.DataSource = branchItems; branches.DisplayMember = "Name";
                folderItems = await client.Folders(p.Id);
                var roots = folderItems.Where(x => String.IsNullOrEmpty(x.ParentId)).ToList();
                folders.DataSource = roots; folders.DisplayMember = "Name";
                if (branchItems.Count > 0) await LoadDocuments();
            }
            catch (Exception ex) { SetStatus("Ошибка загрузки проекта: " + ex.Message); }
            finally { UseWaitCursor = false; }
        }
        private async Task LoadDocuments()
        {
            var f = folders.SelectedItem as ApiItem; var b = branches.SelectedItem as ApiItem;
            if (f == null || b == null || client == null) return;
            try
            {
                documentItems = await client.Documents(f.Id, b.Id);
                documents.DataSource = documentItems; documents.DisplayMember = "Name";
                if (documentItems.Count > 0) await LoadVersions();
            }
            catch (Exception ex) { SetStatus("Ошибка загрузки документов: " + ex.Message); }
        }
        private async Task LoadVersions()
        {
            var d = documents.SelectedItem as ApiItem; var b = branches.SelectedItem as ApiItem;
            if (d == null || b == null || client == null) { versions.DataSource = null; return; }
            try { versionItems = await client.Versions(d.Id, b.Id); versions.DataSource = versionItems; versions.DisplayMember = "Name"; }
            catch (Exception ex) { SetStatus("Ошибка истории: " + ex.Message); }
        }
        private async Task ExecuteAction()
        {
            try
            {
                UseWaitCursor = true;
                if (client == null) throw new InvalidOperationException("Сначала подключитесь к серверу.");
                var b = branches.SelectedItem as ApiItem;
                if (b == null) throw new InvalidOperationException("Выберите ветку.");
                if (uploadMode)
                {
                    if (String.IsNullOrWhiteSpace(activePath) || !File.Exists(activePath)) throw new InvalidOperationException("Сначала сохраните документ на диск в Office.");
                    var f = folders.SelectedItem as ApiItem; if (f == null) throw new InvalidOperationException("Выберите папку.");
                    var d = documents.SelectedItem as ApiItem;
                    string result = d != null
                        ? await client.UploadVersion(d.Id, b.Id, activePath, comment.Text)
                        : await client.UploadNew(f.Id, b.Id, activePath, comment.Text);
                    MessageBox.Show("Ответ DocFlow:\r\n" + result, "DocFlow", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    await LoadDocuments();
                }
                else
                {
                    var d = documents.SelectedItem as ApiItem; var v = versions.SelectedItem as ApiItem;
                    if (d == null || v == null) throw new InvalidOperationException("Выберите документ и версию.");
                    string safeName = Path.GetFileName(d.Name);
                    string destination = Path.Combine(Path.GetTempPath(), "DocFlow", Guid.NewGuid().ToString("N"), safeName);
                    Directory.CreateDirectory(Path.GetDirectoryName(destination));
                    await client.Download(v.Id, destination);
                    Process.Start(new ProcessStartInfo(destination) { UseShellExecute = true });
                    SetStatus("Версия загружена: " + destination);
                }
            }
            catch (Exception ex) { MessageBox.Show(ex.Message, "DocFlow — ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error); }
            finally { UseWaitCursor = false; }
        }
    }
}