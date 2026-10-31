import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Folder, FileText, Search, Plus, Upload, Clock3, GitBranch, ShieldCheck, LogOut, ChevronRight, HardDrive, Users, Trash2, Download, Eye, Pencil } from 'lucide-react';
import './style.css';

const api = async (path: string, init: RequestInit = {}) => {
  const res = await fetch(`/api${path}`, { credentials: 'include', ...init });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const d = data.detail;
    throw new Error((typeof d === 'string' ? d : Array.isArray(d) ? d.map((x: any) => x.msg).join('; ') : '') || `Ошибка ${res.status}`);
  }
  return res.json().catch(() => null);
};
const post = (path: string, body: any, method = 'POST') =>
  api(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const fmt = (s?: string | null) => (s ? new Date(s).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : '—');
const fmtSize = (n: number) => (n < 1024 ? `${n} Б` : n < 1048576 ? `${(n / 1024).toFixed(1)} КБ` : `${(n / 1048576).toFixed(2)} МБ`);
const ROLE: any = { admin: 'Администратор', project_manager: 'Руководитель', member: 'Участник', observer: 'Наблюдатель', manager: 'Руководитель проекта' };
const STATUS: any = { added: 'Добавлен', modified: 'Изменён', removed: 'Удалён', conflict: 'Конфликт' };

function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal ${wide ? 'wide' : ''}`} onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>×</button>
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}

function Segs({ s }: { s: any[] }) {
  return <>{(s || []).map((x, i) => (x[1] ? <mark key={i}>{x[0]}</mark> : <span key={i}>{x[0]}</span>))}</>;
}

function ImgDiff({ d, a, b }: { d: any; a?: string | null; b?: string | null }) {
  const meta = (m: any) => (m ? `${m.w && m.h ? `${m.w}×${m.h}, ` : ''}${fmtSize(m.size)}` : '');
  return (
    <div className="img-diff">
      <div className="diff-head">
        {d.same ? <b>Изображения идентичны</b> : d.a && d.b ? (
          d.changed_pct === 0 ? <b>Файлы различаются, но визуально пиксели совпадают</b>
          : d.changed_pct !== undefined ? <><b className="del-t">Изменено {d.changed_pct}% пикселей</b>{d.resized && <span> · размеры разные, «стало» приведено к размеру «было»</span>}</> : <b>Изображения различаются</b>
        ) : d.b ? <b className="add-t">Новое изображение</b> : <b className="del-t">Изображение удалено</b>}
      </div>
      {d.error && <div className="notice">{d.error}</div>}
      <div className="img-trio">
        {a && <figure><figcaption>Было · {meta(d.a)}</figcaption><img src={`/api/versions/${a}/view`} /></figure>}
        {b && <figure><figcaption>Стало · {meta(d.b)}</figcaption><img src={`/api/versions/${b}/view`} /></figure>}
        {a && b && !d.same && d.changed_pct !== undefined && <figure><figcaption>Отличия (красным)</figcaption><img src={`/api/imgdiff?a=${a}&b=${b}`} /></figure>}
      </div>
    </div>
  );
}

function Thumbs({ items, ver, title, cls }: { items: any[]; ver?: string | null; title: string; cls: string }) {
  if (!items.length || !ver) return null;
  return (
    <div className="thumbs-block"><div className={`thumbs-title ${cls}`}>{title}</div>
      <div className="thumbs">{items.map(m => <figure key={m.h}><img src={`/api/versions/${ver}/media/${m.h}`} alt={m.name} /><figcaption>{m.name} · {fmtSize(m.size)}</figcaption></figure>)}</div></div>
  );
}

function DiffView({ a, b }: { a?: string | null; b?: string | null }) {
  const [d, setD] = useState<any>(null), [err, setErr] = useState(''), [full, setFull] = useState(false);
  useEffect(() => {
    setD(null); setErr('');
    const q = new URLSearchParams();
    if (a) q.set('a', a);
    if (b) q.set('b', b);
    if (full) q.set('full', 'true');
    api('/diff?' + q.toString()).then(setD).catch(e => setErr(e.message));
  }, [a, b, full]);
  if (err) return <div className="notice">{err}</div>;
  if (!d) return <div className="muted pad">Загрузка изменений…</div>;
  if (d.kind === 'image') return <ImgDiff d={d} a={a} b={b} />;
  if (d.kind === 'binary') return <div className="muted pad">Для этого типа файла (PDF, Excel, старые .doc/.vsd и т. п.) сравнение содержимого недоступно. {d.same ? 'Файлы идентичны.' : `Файлы различаются (${fmtSize(d.size_a)} → ${fmtSize(d.size_b)}).`}</div>;
  if (d.kind === 'toolarge') return <div className="muted pad">Файл слишком большой для построчного сравнения.</div>;
  const st = d.stats, im = d.images || { added: [], removed: [] };
  const hasImg = im.added.length || im.removed.length;
  const noText = !st.added_lines && !st.removed_lines;
  return (
    <div>
      {hasImg > 0 && (
        <div className="img-changes">
          <b>Изображения в файле: {im.removed.length && im.added.length ? 'заменены' : im.added.length ? 'добавлены' : 'удалены'}</b>
          <Thumbs items={im.removed} ver={a} title="Было" cls="del-t" />
          <Thumbs items={im.added} ver={b} title="Стало" cls="add-t" />
        </div>
      )}
      {noText ? <div className="muted pad">{hasImg ? 'Текст не изменился — изменились только изображения.' : 'Содержимое не отличается.'}</div> : (
        <div className="diff">
          <div className="diff-head">
            <b className="add-t">+{st.added_lines}</b> <b className="del-t">−{st.removed_lines}</b> строк · символов: <b className="add-t">+{st.added_chars}</b> <b className="del-t">−{st.removed_chars}</b>
            <button className="text-button" onClick={() => setFull(!full)}>{full ? 'Только изменения' : 'Показать весь файл'}</button>
          </div>
          {d.kind === 'docx' && <div className="muted pad">Текст Word сравнивается по абзацам; рисунки отмечены как [рисунок хэш, размер] — замена картинки видна как изменение этой отметки.</div>}
          {d.kind === 'visio' && <div className="muted pad">Visio: сравниваются фигуры (номер, имя, текст, положение и размер) и связи между ними.</div>}
          <div className="diff-body">
            {d.rows.map((r: any, i: number) => {
              if (r.t === 'skip') return <div className="dl skip" key={i}>⋯ {r.n} неизменённых строк</div>;
              if (r.t === 'eq') return <div className="dl" key={i}><span className="ln">{r.an}</span><span className="ln">{r.bn}</span><span className="sg"> </span><code><Segs s={r.a} /></code></div>;
              if (r.t === 'del') return <div className="dl del" key={i}><span className="ln">{r.an}</span><span className="ln" /><span className="sg">−</span><code><Segs s={r.a} /></code></div>;
              if (r.t === 'add') return <div className="dl add" key={i}><span className="ln" /><span className="ln">{r.bn}</span><span className="sg">+</span><code><Segs s={r.b} /></code></div>;
              return (
                <React.Fragment key={i}>
                  <div className="dl del"><span className="ln">{r.an}</span><span className="ln" /><span className="sg">−</span><code><Segs s={r.a} /></code></div>
                  <div className="dl add"><span className="ln" /><span className="ln">{r.bn}</span><span className="sg">+</span><code><Segs s={r.b} /></code></div>
                </React.Fragment>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function eventText(e: any) {
  const d = e.details || {};
  switch (e.type) {
    case 'document.deleted': return `Удалён файл «${d.name}»${d.branch ? ` в ветке «${d.branch}»` : ''}`;
    case 'folder.created': return `Создана папка «${d.name}»`;
    case 'folder.renamed': return `Папка «${d.from}» переименована в «${d.to}»`;
    case 'folder.deleted': return `Удалена папка «${d.name}» (папок: ${d.folders}, файлов: ${d.documents})`;
    case 'branch.created': return `Создана ветка «${d.name}» от «${d.from}»`;
    case 'branch.deleted': return `Удалена ветка «${d.name}»`;
    case 'branch.merged': return `Слияние «${d.from}» → «${d.to}» (файлов: ${d.documents})`;
    case 'project.created': return `Создан проект «${d.name}»${d.template ? ` по шаблону «${d.template}»` : ''}`;
    case 'member.added': return 'Участник добавлен в проект';
    case 'member.removed': return 'Участник удалён из проекта';
    default: return e.type;
  }
}

function History({ projectId, branchId, documentId, branches }: { projectId?: string; branchId?: string; documentId?: string; branches?: any[] }) {
  const [items, setItems] = useState<any[] | null>(null), [open, setOpen] = useState<string | null>(null), [err, setErr] = useState('');
  const [bf, setBf] = useState('');
  useEffect(() => {
    setItems(null);
    const q = new URLSearchParams();
    if (projectId) q.set('project_id', projectId);
    if (bf || branchId) q.set('branch_id', bf || branchId || '');
    if (documentId) q.set('document_id', documentId);
    api('/history?' + q.toString()).then(setItems).catch(e => setErr(e.message));
  }, [projectId, branchId, documentId, bf]);
  if (err) return <div className="notice">{err}</div>;
  if (!items) return <div className="muted pad">Загрузка…</div>;
  return (
    <div className="history">
      {branches && !branchId && (
        <div className="hist-filter">Ветка: <select value={bf} onChange={e => setBf(e.target.value)}><option value="">Все</option>{branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></div>
      )}
      {!items.length && <div className="muted pad">Пока нет изменений</div>}
      {items.map((it, i) => it.kind === 'event' ? (
        <div className="hist-row event" key={i}><div className="dot" /><div><b>{eventText(it)}</b><small>{it.author} · {fmt(it.at)}{it.project ? ` · ${it.project}` : ''}</small></div></div>
      ) : (
        <div key={it.id}>
          <div className="hist-row">
            <div className="dot v" />
            <div className="hist-main">
              <b>{it.comment || 'Без комментария'}</b>
              <small>{it.name} · v{it.version_number}{it.branch ? ` · ветка «${it.branch}»` : ''} · {it.author} · {fmt(it.at)}{it.project && !projectId ? ` · ${it.project}` : ''}{it.folder ? ` · ${it.folder}` : ''}</small>
            </div>
            <button className="text-button" onClick={() => setOpen(open === it.id ? null : it.id)}>{open === it.id ? 'Скрыть' : 'Изменения'}</button>
          </div>
          {open === it.id && <DiffView a={it.prev_id} b={it.id} />}
        </div>
      ))}
    </div>
  );
}

function MergeModal({ src, branches, onClose, onDone }: { src: any; branches: any[]; onClose: () => void; onDone: (m: string) => void }) {
  const others = branches.filter(b => b.id !== src.id);
  const [target, setTarget] = useState<string>((others.find(b => b.is_default) || others[0])?.id || '');
  const [plan, setPlan] = useState<any>(null), [res, setRes] = useState<any>({}), [open, setOpen] = useState<string | null>(null);
  const [msg, setMsg] = useState(''), [err, setErr] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!target) return;
    setPlan(null); setErr(''); setRes({});
    api(`/branches/${src.id}/compare?target_id=${target}`).then(setPlan).catch(e => setErr(e.message));
  }, [target]);
  const unresolved = plan ? plan.items.filter((i: any) => i.status === 'conflict' && !i.auto && !res[i.document_id]).length : 0;
  const go = async () => {
    setBusy(true);
    try {
      const r = await post(`/branches/${src.id}/merge`, { target_id: target, resolutions: res, message: msg });
      onDone(`Слияние выполнено, файлов обновлено: ${r.applied}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal title={`Слияние ветки «${src.name}»`} onClose={onClose} wide>
      {!others.length ? <p>Нет других веток для слияния.</p> : <>
        <label>Влить в ветку
          <select value={target} onChange={e => setTarget(e.target.value)}>{others.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select>
        </label>
        {err && <div className="notice">{err}</div>}
        {!plan && !err && <div className="muted pad">Сравнение…</div>}
        {plan && !plan.items.length && <div className="muted pad">Различий нет — сливать нечего.</div>}
        {plan && plan.items.map((i: any) => (
          <div className="merge-item" key={i.document_id}>
            <div className="merge-top">
              <span className={`badge ${i.status}`}>{STATUS[i.status]}</span>
              <b>{i.name}</b><small>{i.folder}</small>
              {i.status !== 'removed' && <button className="text-button" onClick={() => setOpen(open === i.document_id ? null : i.document_id)}>Изменения</button>}
            </div>
            {i.status === 'conflict' && (
              <div className="conflict">
                {i.auto ? <span>Правки в разных местах — будут объединены автоматически. </span> : <span>Файл изменён в обеих ветках. Выберите версию: </span>}
                <label className="inline"><input type="radio" checked={res[i.document_id] === 'source'} onChange={() => setRes({ ...res, [i.document_id]: 'source' })} /> из «{src.name}»</label>
                <label className="inline"><input type="radio" checked={res[i.document_id] === 'target'} onChange={() => setRes({ ...res, [i.document_id]: 'target' })} /> оставить в целевой</label>
                {i.auto && <label className="inline"><input type="radio" checked={!res[i.document_id] || res[i.document_id] === 'auto'} onChange={() => { const r = { ...res }; delete r[i.document_id]; setRes(r); }} /> объединить</label>}
              </div>
            )}
            {open === i.document_id && <DiffView a={i.target_version} b={i.source_version} />}
          </div>
        ))}
        <label>Комментарий к слиянию<input value={msg} onChange={e => setMsg(e.target.value)} /></label>
        <div className="modal-actions">
          <button className="secondary" onClick={onClose}>Отмена</button>
          <button className="primary" disabled={busy || !plan || !plan.items.length || unresolved > 0} onClick={go}>{unresolved ? `Разрешите конфликты (${unresolved})` : 'Выполнить слияние'}</button>
        </div>
      </>}
    </Modal>
  );
}

function App() {
  const [user, setUser] = useState<any>(null), [login, setLogin] = useState(''), [password, setPassword] = useState('');
  const [view, setView] = useState('home'), [tab, setTab] = useState('files');
  const [projects, setProjects] = useState<any[]>([]), [project, setProject] = useState<any>(null);
  const [folders, setFolders] = useState<any[]>([]), [folder, setFolder] = useState<any>(null), [docs, setDocs] = useState<any[]>([]);
  const [branches, setBranches] = useState<any[]>([]), [branchId, setBranchId] = useState('');
  const [notice, setNotice] = useState(''), [search, setSearch] = useState(''), [modal, setModal] = useState<string>('');
  const [newName, setNewName] = useState(''), [tplId, setTplId] = useState(''), [templates, setTemplates] = useState<any[]>([]);
  const [files, setFiles] = useState<File[]>([]), [comment, setComment] = useState(''), [loading, setLoading] = useState(false);
  const [doc, setDoc] = useState<any>(null), [preview, setPreview] = useState<any>(null), [cmp, setCmp] = useState<any>(null);
  const [mergeSrc, setMergeSrc] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]), [editUser, setEditUser] = useState<any>(null), [uf, setUf] = useState<any>({ role: 'member' });
  const [members, setMembers] = useState<any[]>([]), [directory, setDirectory] = useState<any[]>([]), [mf, setMf] = useState<any>({ role: 'member' });
  const [pw, setPw] = useState<any>({ cur: '', n1: '', n2: '' });
  const [tf, setTf] = useState<any>({ name: '', paths: '' });
  const canManage = user && (user.role === 'admin' || user.role === 'project_manager');
  const branch = branches.find(b => b.id === branchId);
  const fail = (e: any) => setNotice(e.message || String(e));

  useEffect(() => { api('/auth/me').then(setUser).catch(() => {}); }, []);
  useEffect(() => { if (user) { refreshProjects(); if (user.must_change_password) setModal('password'); } }, [user]);
  useEffect(() => { if (folder && branchId) refreshDocs(); }, [folder, branchId]);
  useEffect(() => {
    if (modal !== 'upload') return;
    const onPaste = (e: ClipboardEvent) => {
      const t = e.target as HTMLInputElement | null;
      if (t && (t.tagName === 'TEXTAREA' || (t.tagName === 'INPUT' && t.type !== 'file'))) return;
      const cd = e.clipboardData;
      if (!cd) return;
      const dg = new Date().toISOString().replace(/\D/g, '');
      const stamp = `${dg.slice(0, 8)}_${dg.slice(8, 14)}_${dg.slice(14, 17)}`;
      const got: File[] = [];
      Array.from(cd.files).forEach((f, k) => {
        const generic = !f.name || /^image\.\w+$/i.test(f.name);
        const ext = (f.type.split('/')[1] || 'png').replace('jpeg', 'jpg').replace('svg+xml', 'svg');
        got.push(generic ? new File([f], `Снимок_${stamp}${k ? '_' + k : ''}.${ext}`, { type: f.type }) : f);
      });
      if (!got.length) {
        const tx = cd.getData('text/plain');
        if (tx) got.push(new File([tx], `Текст_${stamp}.txt`, { type: 'text/plain' }));
      }
      if (got.length) { e.preventDefault(); setFiles(prev => [...prev, ...got]); }
    };
    document.addEventListener('paste', onPaste);
    return () => document.removeEventListener('paste', onPaste);
  }, [modal]);

  const refreshProjects = () => api('/projects').then(setProjects).catch(fail);
  const refreshTree = async (pid = project?.id) => setFolders(await api(`/projects/${pid}/tree`));
  const refreshBranches = async (pid = project?.id) => { const b = await api(`/projects/${pid}/branches`); setBranches(b); return b; };
  const refreshDocs = () => api(`/folders/${folder.id}/documents?branch_id=${branchId}`).then(setDocs).catch(fail);

  const openProject = async (p: any) => {
    try {
      setProject(p); setView('project'); setTab('files'); setFolder(null); setDocs([]);
      const [b, t] = await Promise.all([api(`/projects/${p.id}/branches`), api(`/projects/${p.id}/tree`)]);
      setBranches(b); setFolders(t); setBranchId((b.find((x: any) => x.is_default) || b[0])?.id || '');
    } catch (e) { fail(e); }
  };
  const goHome = () => { setView('home'); setProject(null); setFolder(null); };
  const signIn = async (e: React.FormEvent) => {
    e.preventDefault();
    try { setUser(await post('/auth/login', { username: login, password })); setNotice(''); } catch (err) { fail(err); }
  };
  const signOut = async () => { await api('/auth/logout', { method: 'POST' }).catch(() => {}); setUser(null); goHome(); };
  const close = () => { setModal(''); setNewName(''); setFiles([]); setComment(''); };
  const run = async (fn: () => Promise<any>, ok?: string) => {
    try { setLoading(true); await fn(); if (ok) setNotice(ok); } catch (e) { fail(e); } finally { setLoading(false); }
  };

  const openNewProject = async () => { setTemplates(await api('/templates').catch(() => [])); setTplId(''); setModal('project'); };
  const createProject = () => run(async () => {
    await post('/projects', { name: newName, description: '', template_id: tplId || null });
    close(); await refreshProjects();
  }, 'Проект создан');
  const createFolder = () => run(async () => {
    await post(`/projects/${project.id}/folders`, { name: newName, parent_id: folder?.id ?? null });
    close(); await refreshTree();
  }, 'Папка создана');
  const renameFolder = (f: any) => {
    const name = window.prompt('Новое название папки', f.name);
    if (name && name.trim() && name !== f.name) run(async () => { await post(`/folders/${f.id}`, { name }, 'PATCH'); await refreshTree(); }, 'Папка переименована');
  };
  const deleteFolder = (f: any) => {
    if (!window.confirm(`Удалить папку «${f.name}» вместе с вложенными папками и всеми файлами? Это действие применяется ко всем веткам.`)) return;
    run(async () => {
      const r = await api(`/folders/${f.id}`, { method: 'DELETE' });
      if (folder && (folder.id === f.id || isInside(folder.id, f.id))) { setFolder(null); setDocs([]); }
      await refreshTree(); await refreshBranches();
      setNotice(`Удалено папок: ${r.folders}, файлов: ${r.documents}`);
    });
  };
  const isInside = (id: string, ancestor: string): boolean => {
    let cur = folders.find(x => x.id === id);
    while (cur) { if (cur.parent_id === ancestor) return true; cur = folders.find(x => x.id === cur.parent_id); }
    return false;
  };
  const upload = () => run(async () => {
    const msgs: string[] = [];
    for (const f of files) {
      const fd = new FormData(); fd.append('file', f); fd.append('comment', comment);
      const r = await api(`/folders/${folder.id}/documents?branch_id=${branchId}`, { method: 'POST', body: fd });
      msgs.push(r.unchanged ? `«${f.name}»: без изменений` : r.updated ? `«${f.name}»: обновлён до v${r.version_number}` : `«${f.name}»: загружен`);
    }
    close(); await refreshDocs(); setNotice(msgs.join('; '));
  });
  const openDoc = async (d: any) => {
    try { setPreview(null); setCmp(null); setDoc(await api(`/documents/${d.id}?branch_id=${branchId}`)); setModal('doc'); } catch (e) { fail(e); }
  };
  const reloadDoc = async () => { setDoc(await api(`/documents/${doc.id}?branch_id=${branchId}`)); await refreshDocs(); };
  const deleteDoc = (d: any) => {
    if (!window.confirm(`Удалить файл «${d.name}» из ветки «${branch?.name}»? История версий сохранится.`)) return;
    run(async () => { await api(`/documents/${d.id}?branch_id=${branchId}`, { method: 'DELETE' }); if (modal === 'doc') close(); await refreshDocs(); }, 'Файл удалён');
  };
  const newVersion = (f: File | null) => {
    if (!f) return;
    run(async () => {
      const fd = new FormData(); fd.append('file', f); fd.append('comment', comment);
      const r = await api(`/documents/${doc.id}/versions?branch_id=${branchId}`, { method: 'POST', body: fd });
      setComment(''); await reloadDoc(); setNotice(r.unchanged ? r.message : `Создана версия ${r.version_number}`);
    });
  };
  const restore = (v: any) => {
    if (!window.confirm(`Восстановить версию ${v.version_number} как новую? Старые версии сохранятся.`)) return;
    run(async () => { await api(`/versions/${v.id}/restore?branch_id=${branchId}`, { method: 'POST' }); await reloadDoc(); }, 'Создана новая версия из выбранной');
  };
  const showText = async (v: any) => { try { setCmp(null); setPreview({ ...(await api(`/versions/${v.id}/text`)), v }); } catch (e) { fail(e); } };
  const createBranch = () => run(async () => {
    const r = await post(`/projects/${project.id}/branches`, { name: newName, from_branch_id: branchId });
    close(); await refreshBranches(); setBranchId(r.id);
  }, 'Ветка создана');
  const deleteBranch = (b: any) => {
    if (!window.confirm(`Удалить ветку «${b.name}»? Неслитые изменения будут потеряны (версии останутся в истории).`)) return;
    run(async () => { await api(`/branches/${b.id}`, { method: 'DELETE' }); const nb = await refreshBranches(); if (branchId === b.id) setBranchId(nb.find((x: any) => x.is_default)?.id); }, 'Ветка удалена');
  };
  const openMembers = async () => {
    try {
      setMembers(await api(`/projects/${project.id}/members`));
      if (canManage) setDirectory(await api('/users/directory'));
      setMf({ role: 'member', user_id: '' }); setModal('members');
    } catch (e) { fail(e); }
  };
  const saveAsTemplate = () => {
    const name = window.prompt('Название шаблона (будет сохранена структура папок проекта)');
    if (name && name.trim()) run(() => post('/templates', { name, from_project_id: project.id }), 'Шаблон сохранён');
  };
  const openUsers = async () => { setView('users'); setProject(null); try { setUsers(await api('/users')); } catch (e) { fail(e); } };
  const openTemplates = async () => { setView('templates'); setProject(null); try { setTemplates(await api('/templates')); } catch (e) { fail(e); } };
  const changePassword = () => {
    if (pw.n1 !== pw.n2) return setNotice('Новые пароли не совпадают');
    run(async () => {
      await post('/auth/change-password', { current_password: pw.cur, new_password: pw.n1 });
      setPw({ cur: '', n1: '', n2: '' }); setModal(''); setUser({ ...user, must_change_password: false });
    }, 'Пароль изменён');
  };
  const saveUser = () => run(async () => {
    if (editUser) {
      const body: any = { full_name: uf.full_name, role: uf.role, status: uf.status, email: uf.email };
      if (uf.new_password) body.new_password = uf.new_password;
      await post(`/users/${editUser.id}`, body, 'PATCH');
    } else {
      await post('/users', { full_name: uf.full_name, username: uf.username, password: uf.password, role: uf.role, email: uf.email });
    }
    setModal(''); setEditUser(null); setUsers(await api('/users'));
  }, 'Сохранено');
  const saveTemplate = () => run(async () => {
    await post('/templates', { name: tf.name, paths: tf.paths.split('\n') });
    setTf({ name: '', paths: '' }); setTemplates(await api('/templates'));
  }, 'Шаблон создан');

  // ---- хлебные крошки ----
  const crumbs: any[] = [];
  { let cur = folder; const seen = new Set();
    while (cur && !seen.has(cur.id)) { seen.add(cur.id); crumbs.unshift(cur); cur = folders.find(x => x.id === cur.parent_id); } }
  const children = (parent: string | null) => folders.filter(f => f.parent_id === parent);
  const tree = (parent: string | null, depth = 0): React.ReactNode => children(parent).map(f => (
    <React.Fragment key={f.id}>
      <div className={`tree-row ${folder?.id === f.id ? 'selected' : ''}`} style={{ paddingLeft: 10 + depth * 16 }}>
        <button className="tree-item" onClick={() => setFolder(f)}><Folder size={15} /><span>{f.name}</span></button>
        <button className="icon-btn" title="Переименовать" onClick={() => renameFolder(f)}><Pencil size={13} /></button>
        <button className="icon-btn danger" title="Удалить папку" onClick={() => deleteFolder(f)}><Trash2 size={13} /></button>
      </div>
      {tree(f.id, depth + 1)}
    </React.Fragment>
  ));

  if (!user) return (
    <div className="login-wrap"><form className="login-card" onSubmit={signIn}>
      <div className="brand large"><div className="brand-icon"><HardDrive /></div><div><b>DocFlow</b><small>Документы отдела</small></div></div>
      <h1>Вход в систему</h1><p>Внутреннее хранилище проектов и документации</p>
      <label>Логин<input value={login} onChange={e => setLogin(e.target.value)} autoComplete="username" required /></label>
      <label>Пароль<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required /></label>
      {notice && <div className="notice">{notice}</div>}
      <button className="primary full">Войти</button>
    </form></div>
  );

  const visibleDocs = docs.filter(d => d.name.toLowerCase().includes(search.toLowerCase()));
  const existingNames = new Set(docs.map(d => d.name));

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-icon"><HardDrive size={20} /></div><div><b>DocFlow</b><small>Рабочее пространство</small></div></div>
        <div className="nav-label">РАБОЧЕЕ</div>
        <button className={view === 'home' ? 'nav-item active' : 'nav-item'} onClick={goHome}><HardDrive size={17} />Обзор</button>
        <button className={view === 'project' && tab === 'branches' ? 'nav-item active' : 'nav-item'} onClick={() => project ? (setView('project'), setTab('branches')) : setNotice('Сначала откройте проект — ветки создаются внутри проекта.')}><GitBranch size={17} />Ветки</button>
        <button className={view === 'history' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('history'); setProject(null); }}><Clock3 size={17} />История</button>
        {canManage && <button className={view === 'templates' ? 'nav-item active' : 'nav-item'} onClick={openTemplates}><Folder size={17} />Шаблоны папок</button>}
        {user.role === 'admin' && <button className={view === 'users' ? 'nav-item active' : 'nav-item'} onClick={openUsers}><Users size={17} />Пользователи</button>}
        <div className="nav-label projects-label">ПРОЕКТЫ {canManage && <button onClick={openNewProject} title="Создать проект"><Plus size={15} /></button>}</div>
        {projects.map(p => <button key={p.id} className={`project-link ${project?.id === p.id ? 'active' : ''}`} onClick={() => openProject(p)}><span className="project-dot" /><span>{p.name}</span></button>)}
        <div className="sidebar-bottom"><div className="user-mini">
          <div className="avatar">{user.full_name?.slice(0, 1) || 'U'}</div>
          <div className="user-meta"><b>{user.full_name}</b><small>{ROLE[user.role] || user.role}</small></div>
          <button onClick={() => setModal('password')} title="Сменить пароль"><ShieldCheck size={16} /></button>
          <button onClick={signOut} title="Выйти"><LogOut size={16} /></button>
        </div></div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            <button className="crumb" onClick={goHome}>DocFlow</button>
            {view === 'project' && project && <><ChevronRight size={15} /><button className="crumb" onClick={() => { setTab('files'); setFolder(null); setDocs([]); }}>{project.name}</button></>}
            {view === 'project' && crumbs.map(c => <React.Fragment key={c.id}><ChevronRight size={15} /><button className="crumb" onClick={() => { setTab('files'); setFolder(c); }}>{c.name}</button></React.Fragment>)}
            {view === 'history' && <><ChevronRight size={15} /><b>История</b></>}
            {view === 'users' && <><ChevronRight size={15} /><b>Пользователи</b></>}
            {view === 'templates' && <><ChevronRight size={15} /><b>Шаблоны папок</b></>}
          </div>
          <div className="top-actions"><div className="searchbox"><Search size={16} /><input placeholder="Поиск в текущем списке..." value={search} onChange={e => setSearch(e.target.value)} /></div></div>
        </header>
        {notice && <div className="toast" onClick={() => setNotice('')}>{notice}<button>×</button></div>}

        {view === 'home' && (
          <section className="content">
            <div className="welcome"><div><div className="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</div><h1>Добро пожаловать, {user.full_name.split(' ')[0]}</h1><p>Все проекты и документы отдела — в одном месте.</p></div>
              {canManage && <button className="primary" onClick={openNewProject}><Plus size={16} />Новый проект</button>}</div>
            <div className="project-grid">
              {projects.filter(p => p.name.toLowerCase().includes(search.toLowerCase())).map(p => (
                <button className="project-card" key={p.id} onClick={() => openProject(p)}>
                  <div className="card-top"><div className="project-symbol"><Folder /></div></div>
                  <h3>{p.name}</h3><p>{p.description || 'Описание проекта не добавлено'}</p>
                  <div className="card-foot"><span>Открыть проект <ChevronRight size={15} /></span></div>
                </button>
              ))}
              {!projects.length && <div className="empty-state"><h3>Пока нет проектов</h3><p>{canManage ? 'Создайте первый проект.' : 'Администратор должен добавить вас в проект.'}</p></div>}
            </div>
          </section>
        )}

        {view === 'history' && <section className="content"><div className="section-heading"><div><h2>История изменений</h2><p>Все версии файлов и операции по доступным вам проектам.</p></div></div><History /></section>}

        {view === 'users' && (
          <section className="content">
            <div className="section-heading"><div><h2>Пользователи</h2><p>Создание учётных записей, роли, сброс пароля и блокировка.</p></div>
              <button className="primary" onClick={() => { setEditUser(null); setUf({ role: 'member' }); setModal('user'); }}><Plus size={16} />Новый пользователь</button></div>
            <div className="table-wrap"><table><thead><tr><th>ФИО</th><th>Логин</th><th>Роль</th><th>Статус</th><th>Последний вход</th><th /></tr></thead><tbody>
              {users.map(u => <tr key={u.id}><td><b>{u.full_name}</b></td><td>{u.username}</td><td>{ROLE[u.role]}</td><td>{u.status === 'active' ? 'Активен' : 'Заблокирован'}</td><td>{fmt(u.last_login_at)}</td>
                <td><button className="text-button" onClick={() => { setEditUser(u); setUf({ ...u, new_password: '' }); setModal('user'); }}>Изменить</button></td></tr>)}
            </tbody></table></div>
          </section>
        )}

        {view === 'templates' && (
          <section className="content">
            <div className="section-heading"><div><h2>Шаблоны папок</h2><p>При создании проекта по шаблону сразу появляется заданный набор папок. Вложенность — через «/».</p></div></div>
            <div className="tpl-grid">
              <div className="panel-box"><h3>Новый шаблон</h3>
                <label>Название<input value={tf.name} onChange={e => setTf({ ...tf, name: e.target.value })} placeholder="Например, Проектная документация" /></label>
                <label>Папки (по одной в строке)<textarea rows={8} value={tf.paths} onChange={e => setTf({ ...tf, paths: e.target.value })} placeholder={'01 Исходные данные\n02 Чертежи/Архитектура\n02 Чертежи/Конструкции\n03 Переписка'} /></label>
                <button className="primary" disabled={!tf.name.trim() || !tf.paths.trim() || loading} onClick={saveTemplate}>Создать шаблон</button>
                <p className="muted">Шаблон можно также сохранить из готового проекта кнопкой «Сохранить как шаблон».</p></div>
              <div>{templates.map(t => <div className="panel-box" key={t.id}><div className="tpl-head"><h3>{t.name}</h3>
                <button className="icon-btn danger" title="Удалить шаблон" onClick={() => window.confirm('Удалить шаблон?') && run(async () => { await api(`/templates/${t.id}`, { method: 'DELETE' }); setTemplates(await api('/templates')); })}><Trash2 size={15} /></button></div>
                <ul className="tpl-list">{t.paths.map((p: string, i: number) => <li key={i}><Folder size={13} />{p}</li>)}</ul></div>)}
                {!templates.length && <div className="muted pad">Шаблонов пока нет</div>}</div>
            </div>
          </section>
        )}

        {view === 'project' && project && (
          <section className="content project-view">
            <div className="project-header">
              <div><div className="eyebrow">ПРОЕКТ</div><h1>{project.name}</h1></div>
              <div className="project-actions">
                <label className="branch-select"><GitBranch size={15} /><select value={branchId} onChange={e => setBranchId(e.target.value)}>{branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
                <button className="secondary" onClick={() => { setNewName(''); setModal('branch'); }}><GitBranch size={16} />Новая ветка</button>
                <button className="secondary" onClick={openMembers}><Users size={16} />Участники</button>
                {canManage && <button className="secondary" onClick={saveAsTemplate}>Сохранить как шаблон</button>}
              </div>
            </div>
            <div className="tabs">{[['files', 'Файлы'], ['branches', 'Ветки'], ['history', 'История']].map(([k, l]) => <button key={k} className={tab === k ? 'tab active' : 'tab'} onClick={() => setTab(k)}>{l}</button>)}</div>

            {tab === 'files' && (
              <div className="workspace">
                <aside className="folder-panel">
                  <div className="panel-title">СТРУКТУРА ПАПОК <button className="icon-btn" title="Новая папка" onClick={() => { setNewName(''); setModal('folder'); }}><Plus size={14} /></button></div>
                  {tree(null)}
                  {!folders.length && <p className="muted pad">Нет папок</p>}
                </aside>
                <div className="files-panel">
                  <div className="files-heading"><div><h2>{folder?.name || 'Выберите папку'}</h2><p>{folder ? `Ветка «${branch?.name}»` : 'Выберите папку слева для просмотра содержимого'}</p></div>
                    {folder && <button className="primary" onClick={() => setModal('upload')}><Upload size={16} />Загрузить файл</button>}</div>
                  {folder && <div className="table-wrap"><table><thead><tr><th>Название</th><th>Версия</th><th>Автор</th><th>Изменён</th><th /></tr></thead><tbody>
                    {visibleDocs.map(d => <tr key={d.id} onClick={() => openDoc(d)}>
                      <td><div className="file-name"><div className="file-icon"><FileText size={17} /></div><div><b>{d.name}</b><small>{d.comment} · {fmtSize(d.size_bytes)}</small></div></div></td>
                      <td><span className="version-badge">v{d.current_version}</span></td><td>{d.author}</td><td>{fmt(d.updated_at)}</td>
                      <td className="row-actions" onClick={e => e.stopPropagation()}>
                        <button className="icon-btn" title="Открыть" onClick={() => openDoc(d)}><Eye size={16} /></button>
                        <a className="icon-btn" title="Скачать" href={`/api/versions/${d.version_id}/download`}><Download size={16} /></a>
                        <button className="icon-btn danger" title="Удалить" onClick={() => deleteDoc(d)}><Trash2 size={16} /></button></td></tr>)}
                  </tbody></table>
                    {!visibleDocs.length && <div className="empty-inline"><FileText /><b>В этой папке пока нет документов</b><span>Загрузите первый файл.</span></div>}</div>}
                </div>
              </div>
            )}

            {tab === 'branches' && (
              <div className="table-wrap"><table><thead><tr><th>Ветка</th><th>Создана</th><th>Автор</th><th>Отличий от main</th><th /></tr></thead><tbody>
                {branches.map(b => <tr key={b.id}>
                  <td><b>{b.name}</b> {b.is_default && <span className="version-badge">основная</span>} {b.id === branchId && <span className="version-badge cur">текущая</span>}</td>
                  <td>{fmt(b.created_at)}</td><td>{b.created_by || '—'}</td><td>{b.is_default ? '—' : `${b.changes_vs_main} файл(ов)`}</td>
                  <td className="row-actions">
                    {b.id !== branchId && <button className="text-button" onClick={() => { setBranchId(b.id); setTab('files'); }}>Переключиться</button>}
                    {branches.length > 1 && <button className="text-button" onClick={() => { setMergeSrc(b); setModal('merge'); }}>Слить в…</button>}
                    {!b.is_default && <button className="icon-btn danger" title="Удалить ветку" onClick={() => deleteBranch(b)}><Trash2 size={15} /></button>}</td></tr>)}
              </tbody></table></div>
            )}

            {tab === 'history' && <History projectId={project.id} branches={branches} />}
          </section>
        )}
      </main>

      {modal === 'project' && <Modal title="Новый проект" onClose={close}>
        <label>Название проекта<input autoFocus value={newName} onChange={e => setNewName(e.target.value)} /></label>
        <label>Шаблон папок<select value={tplId} onChange={e => setTplId(e.target.value)}><option value="">Без шаблона (одна корневая папка)</option>{templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
        <div className="modal-actions"><button className="secondary" onClick={close}>Отмена</button><button className="primary" disabled={!newName.trim() || loading} onClick={createProject}>Создать проект</button></div></Modal>}

      {modal === 'folder' && <Modal title="Новая папка" onClose={close}>
        <p>{folder ? `Вложенная папка внутри «${folder.name}»` : 'Папка верхнего уровня'}</p>
        <label>Название<input autoFocus value={newName} onChange={e => setNewName(e.target.value)} /></label>
        <div className="modal-actions"><button className="secondary" onClick={close}>Отмена</button><button className="primary" disabled={!newName.trim() || loading} onClick={createFolder}>Создать</button></div></Modal>}

      {modal === 'branch' && <Modal title="Новая ветка" onClose={close}>
        <p>Ветка создаётся как копия состояния «{branch?.name}». Правки в ней не затрагивают другие ветки, пока вы не выполните слияние.</p>
        <label>Название ветки<input autoFocus value={newName} onChange={e => setNewName(e.target.value)} placeholder="Например, правки-заказчика" /></label>
        <div className="modal-actions"><button className="secondary" onClick={close}>Отмена</button><button className="primary" disabled={!newName.trim() || loading} onClick={createBranch}>Создать ветку</button></div></Modal>}

      {modal === 'upload' && <Modal title="Загрузить файлы" onClose={close}>
        <p>Ветка «{branch?.name}». Если файл с таким именем уже есть в папке, он обновится новой версией, а не добавится копией.</p>
        <label className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); setFiles(prev => [...prev, ...Array.from(e.dataTransfer.files)]); }}>
          <Upload /><b>Выберите файлы, перетащите их сюда или вставьте из буфера (Ctrl+V)</b>
          <small>Скриншот, скопированный файл или текст — просто нажмите Ctrl+V в этом окне</small>
          <input type="file" multiple onChange={e => { setFiles(prev => [...prev, ...Array.from(e.target.files || [])]); e.target.value = ''; }} /></label>
        {files.map((f, i) => (
          <div className="file-row" key={i}>
            {f.type.startsWith('image/') ? <img src={URL.createObjectURL(f)} className="file-thumb" /> : <FileText size={18} />}
            <input value={f.name} onChange={e => setFiles(files.map((x, k) => (k === i ? new File([x], e.target.value, { type: x.type }) : x)))} />
            <small>{fmtSize(f.size)}</small>
            <button className="icon-btn danger" title="Убрать" onClick={() => setFiles(files.filter((_, k) => k !== i))}><Trash2 size={14} /></button>
          </div>
        ))}
        {files.filter(f => existingNames.has(f.name)).length > 0 && <div className="notice info">Будут обновлены существующие файлы: {files.filter(f => existingNames.has(f.name)).map(f => f.name).join(', ')}</div>}
        <label>Комментарий к версии<input value={comment} onChange={e => setComment(e.target.value)} placeholder="Что изменилось" /></label>
        <div className="modal-actions"><button className="secondary" onClick={close}>Отмена</button><button className="primary" disabled={!files.length || loading} onClick={upload}>{loading ? 'Загрузка…' : `Загрузить${files.length ? ` (${files.length})` : ''}`}</button></div></Modal>}

      {modal === 'doc' && doc && <Modal title={doc.name} onClose={close} wide>
        <p className="muted">{doc.folder} · ветка «{doc.branch}»</p>
        <div className="doc-new"><input value={comment} onChange={e => setComment(e.target.value)} placeholder="Комментарий к новой версии" />
          <label className="secondary file-btn"><Upload size={15} /> Загрузить новую версию<input type="file" hidden onChange={e => { newVersion(e.target.files?.[0] || null); e.target.value = ''; }} /></label></div>
        <div className="version-list">{doc.versions.map((v: any) => (
          <div className="version-row" key={v.id}>
            <div><b>Версия {v.version_number}</b> {v.is_head && <span className="version-badge cur">текущая</span>}<small>{v.comment || 'Без комментария'} · {v.author} · {v.branch ? `ветка «${v.branch}» · ` : ''}{fmt(v.created_at)} · {fmtSize(v.size_bytes)}</small></div>
            <div className="version-actions">
              <button className="text-button" onClick={() => showText(v)}>Просмотр</button>
              {v.prev_id && <button className="text-button" onClick={() => { setPreview(null); setCmp({ a: v.prev_id, b: v.id, title: `Версия ${v.version_number}: что изменилось` }); }}>Изменения</button>}
              {!v.is_head && doc.head_version_id && <button className="text-button" onClick={() => { setPreview(null); setCmp({ a: v.id, b: doc.head_version_id, title: `Версия ${v.version_number} → текущая` }); }}>Сравнить с текущей</button>}
              <a className="text-button" href={`/api/versions/${v.id}/download`}>Скачать</a>
              {!v.is_head && <button className="text-button" onClick={() => restore(v)}>Восстановить</button>}
            </div></div>))}</div>
        {preview && <div className="preview"><div className="diff-head"><b>Версия {preview.v.version_number}</b><button className="text-button" onClick={() => setPreview(null)}>Закрыть</button></div>
          {preview.kind === 'image' ? <img className="pv-img" src={`/api/versions/${preview.v.id}/view`} /> : preview.text === null ? <div className="muted pad">Просмотр этого типа файла недоступен — скачайте файл.</div> : <pre>{preview.text}</pre>}</div>}
        {cmp && <div className="preview"><div className="diff-head"><b>{cmp.title}</b><button className="text-button" onClick={() => setCmp(null)}>Закрыть</button></div><DiffView a={cmp.a} b={cmp.b} /></div>}
        <div className="modal-actions"><button className="secondary danger-btn" onClick={() => deleteDoc(doc)}><Trash2 size={15} /> Удалить из ветки</button><button className="secondary" onClick={close}>Закрыть</button></div></Modal>}

      {modal === 'merge' && mergeSrc && <MergeModal src={mergeSrc} branches={branches} onClose={() => { setModal(''); setMergeSrc(null); }}
        onDone={async m => { setModal(''); setMergeSrc(null); await refreshBranches(); if (folder) await refreshDocs(); setNotice(m); }} />}

      {modal === 'members' && <Modal title="Участники проекта" onClose={close}>
        {members.map(m => <div className="member-row" key={m.user_id}><div><b>{m.full_name}</b><small>{m.username} · {ROLE[m.role] || m.role}</small></div>
          {canManage && <button className="icon-btn danger" onClick={() => run(async () => { await api(`/projects/${project.id}/members/${m.user_id}`, { method: 'DELETE' }); setMembers(await api(`/projects/${project.id}/members`)); })}><Trash2 size={15} /></button>}</div>)}
        {canManage && <div className="member-add"><select value={mf.user_id || ''} onChange={e => setMf({ ...mf, user_id: e.target.value })}><option value="">Выберите сотрудника…</option>{directory.filter(u => !members.some(m => m.user_id === u.id)).map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.username})</option>)}</select>
          <select value={mf.role} onChange={e => setMf({ ...mf, role: e.target.value })}><option value="member">Участник</option><option value="observer">Наблюдатель</option><option value="manager">Руководитель проекта</option></select>
          <button className="primary" disabled={!mf.user_id} onClick={() => run(async () => { await post(`/projects/${project.id}/members`, mf); setMembers(await api(`/projects/${project.id}/members`)); setMf({ ...mf, user_id: '' }); })}>Добавить</button></div>}
        <div className="modal-actions"><button className="secondary" onClick={close}>Закрыть</button></div></Modal>}

      {modal === 'user' && <Modal title={editUser ? `Пользователь: ${editUser.username}` : 'Новый пользователь'} onClose={() => { setModal(''); setEditUser(null); }}>
        <label>ФИО<input value={uf.full_name || ''} onChange={e => setUf({ ...uf, full_name: e.target.value })} /></label>
        {!editUser && <label>Логин<input value={uf.username || ''} onChange={e => setUf({ ...uf, username: e.target.value })} /></label>}
        <label>Эл. почта (необязательно)<input value={uf.email || ''} onChange={e => setUf({ ...uf, email: e.target.value })} /></label>
        <label>Роль<select value={uf.role} onChange={e => setUf({ ...uf, role: e.target.value })}><option value="member">Участник</option><option value="project_manager">Руководитель</option><option value="observer">Наблюдатель</option><option value="admin">Администратор</option></select></label>
        {editUser && <label>Статус<select value={uf.status} onChange={e => setUf({ ...uf, status: e.target.value })}><option value="active">Активен</option><option value="blocked">Заблокирован</option></select></label>}
        <label>{editUser ? 'Новый пароль (оставьте пустым, чтобы не менять)' : 'Стартовый пароль (не менее 12 символов)'}<input type="text" value={(editUser ? uf.new_password : uf.password) || ''} onChange={e => setUf({ ...uf, [editUser ? 'new_password' : 'password']: e.target.value })} /></label>
        <p className="muted">Пользователь сменит стартовый пароль при первом входе.</p>
        <div className="modal-actions"><button className="secondary" onClick={() => { setModal(''); setEditUser(null); }}>Отмена</button><button className="primary" disabled={loading || !uf.full_name} onClick={saveUser}>Сохранить</button></div></Modal>}

      {modal === 'password' && <Modal title="Смена пароля" onClose={() => !user.must_change_password && setModal('')}>
        {user.must_change_password && <div className="notice info">Для продолжения работы смените стартовый пароль.</div>}
        <label>Текущий пароль<input type="password" value={pw.cur} onChange={e => setPw({ ...pw, cur: e.target.value })} /></label>
        <label>Новый пароль (не менее 12 символов)<input type="password" value={pw.n1} onChange={e => setPw({ ...pw, n1: e.target.value })} /></label>
        <label>Повторите новый пароль<input type="password" value={pw.n2} onChange={e => setPw({ ...pw, n2: e.target.value })} /></label>
        <div className="modal-actions">{!user.must_change_password && <button className="secondary" onClick={() => setModal('')}>Отмена</button>}<button className="primary" disabled={loading || !pw.cur || pw.n1.length < 12} onClick={changePassword}>Сменить пароль</button></div></Modal>}
    </div>
  );
}
createRoot(document.getElementById('root')!).render(<App />);
