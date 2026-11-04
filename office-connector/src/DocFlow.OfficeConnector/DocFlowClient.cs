using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace DocFlow.OfficeConnector
{
    public sealed class ApiItem
    {
        public string Id, Name, ParentId, Description, VersionId, Author, Comment, CreatedAt;
        public int VersionNumber;
        public bool IsDefault;
        public override string ToString() { return Name; }
    }

    public sealed class DocFlowClient : IDisposable
    {
        private readonly CookieContainer cookies = new CookieContainer();
        private readonly HttpClient http;
        private readonly JavaScriptSerializer json = new JavaScriptSerializer();
        public string BaseUrl { get; private set; }
        public DocFlowClient(string baseUrl)
        {
            Uri parsed;
            if (!Uri.TryCreate(baseUrl, UriKind.Absolute, out parsed) ||
                (parsed.Scheme != Uri.UriSchemeHttp && parsed.Scheme != Uri.UriSchemeHttps) ||
                !String.IsNullOrEmpty(parsed.UserInfo) || !IsPrivateNetworkHost(parsed.Host))
                throw new ArgumentException("Разрешён только адрес сервера DocFlow в локальной сети: используйте частный IP (10.x.x.x, 172.16-31.x.x, 192.168.x.x) или localhost.");
            BaseUrl = parsed.GetLeftPart(UriPartial.Path).TrimEnd('/');
            var handler = new HttpClientHandler { CookieContainer = cookies, UseCookies = true, AllowAutoRedirect = false, AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate };
            http = new HttpClient(handler) { Timeout = TimeSpan.FromMinutes(5) };
        }
        private static bool IsPrivateNetworkHost(string host)
        {
            if (String.Equals(host, "localhost", StringComparison.OrdinalIgnoreCase)) return true;
            IPAddress ip;
            if (!IPAddress.TryParse(host, out ip)) return false;
            if (ip.IsIPv4MappedToIPv6) ip = ip.MapToIPv4();
            byte[] b = ip.GetAddressBytes();
            if (ip.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)
                return b[0] == 10 || b[0] == 127 || (b[0] == 192 && b[1] == 168) ||
                       (b[0] == 172 && b[1] >= 16 && b[1] <= 31) || (b[0] == 169 && b[1] == 254);
            return IPAddress.IsLoopback(ip) || ip.IsIPv6LinkLocal || (b.Length == 16 && (b[0] & 0xFE) == 0xFC);
        }
        private string Url(string path) { return BaseUrl + path; }
        private async Task<string> Read(HttpResponseMessage response)
        {
            string body = await response.Content.ReadAsStringAsync();
            if (!response.IsSuccessStatusCode) throw new InvalidOperationException("HTTP " + (int)response.StatusCode + ": " + body);
            return body;
        }
        public async Task Login(string username, string password)
        {
            var body = new StringContent(json.Serialize(new { username = username, password = password }));
            body.Headers.ContentType = new MediaTypeHeaderValue("application/json");
            await Read(await http.PostAsync(Url("/api/auth/login"), body));
        }
        public async Task<List<ApiItem>> Projects() { return Items(await Read(await http.GetAsync(Url("/api/projects")))); }
        public async Task<List<ApiItem>> Folders(string projectId) { return Items(await Read(await http.GetAsync(Url("/api/projects/" + projectId + "/tree")))); }
        public async Task<List<ApiItem>> Branches(string projectId) { return Items(await Read(await http.GetAsync(Url("/api/projects/" + projectId + "/branches")))); }
        public async Task<List<ApiItem>> Documents(string folderId, string branchId)
        {
            return Items(await Read(await http.GetAsync(Url("/api/folders/" + folderId + "/documents?branch_id=" + Uri.EscapeDataString(branchId)))));
        }
        public async Task<List<ApiItem>> Versions(string documentId, string branchId)
        {
            var dict = json.Deserialize<Dictionary<string, object>>(await Read(await http.GetAsync(Url("/api/documents/" + documentId + "?branch_id=" + Uri.EscapeDataString(branchId)))));
            var result = new List<ApiItem>();
            foreach (var item in (object[])dict["versions"])
            {
                var d = (Dictionary<string, object>)item;
                result.Add(new ApiItem { Id = Convert.ToString(d["id"]), Name = "Версия " + d["version_number"] + (Convert.ToBoolean(d["is_head"]) ? " (текущая)" : ""), VersionNumber = Convert.ToInt32(d["version_number"]), Comment = Convert.ToString(d["comment"]), Author = Convert.ToString(d["author"]), CreatedAt = Convert.ToString(d["created_at"]) });
            }
            return result;
        }
        public async Task<string> UploadNew(string folderId, string branchId, string filePath, string comment)
        {
            using (var form = new MultipartFormDataContent())
            using (var stream = File.OpenRead(filePath))
            using (var file = new StreamContent(stream))
            {
                file.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
                form.Add(file, "file", Path.GetFileName(filePath)); form.Add(new StringContent(comment ?? ""), "comment");
                return await Read(await http.PostAsync(Url("/api/folders/" + folderId + "/documents?branch_id=" + Uri.EscapeDataString(branchId)), form));
            }
        }
        public async Task<string> UploadVersion(string documentId, string branchId, string filePath, string comment)
        {
            using (var form = new MultipartFormDataContent())
            using (var stream = File.OpenRead(filePath))
            using (var file = new StreamContent(stream))
            {
                file.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
                form.Add(file, "file", Path.GetFileName(filePath)); form.Add(new StringContent(comment ?? ""), "comment");
                return await Read(await http.PostAsync(Url("/api/documents/" + documentId + "/versions?branch_id=" + Uri.EscapeDataString(branchId)), form));
            }
        }
        public async Task Download(string versionId, string destination)
        {
            var response = await http.GetAsync(Url("/api/versions/" + versionId + "/download"));
            if (!response.IsSuccessStatusCode) throw new InvalidOperationException("HTTP " + (int)response.StatusCode + ": " + await response.Content.ReadAsStringAsync());
            using (var input = await response.Content.ReadAsStreamAsync())
            using (var output = File.Create(destination)) await input.CopyToAsync(output);
        }
        private List<ApiItem> Items(string raw)
        {
            var result = new List<ApiItem>();
            foreach (var item in (object[])json.DeserializeObject(raw))
            {
                var d = (Dictionary<string, object>)item;
                result.Add(new ApiItem {
                    Id = Convert.ToString(d["id"]), Name = Convert.ToString(d["name"]),
                    ParentId = d.ContainsKey("parent_id") && d["parent_id"] != null ? Convert.ToString(d["parent_id"]) : null,
                    Description = d.ContainsKey("description") ? Convert.ToString(d["description"]) : "",
                    IsDefault = d.ContainsKey("is_default") && Convert.ToBoolean(d["is_default"])
                });
            }
            return result;
        }
        public void Dispose() { http.Dispose(); }
    }
}