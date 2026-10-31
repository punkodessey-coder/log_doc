from __future__ import annotations

import hashlib
import html as htmllib
import io
import json
import re
import zipfile
from difflib import SequenceMatcher
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, String, Text, DateTime, Boolean, ForeignKey, Integer, BigInteger, select, func
from sqlalchemy import inspect as sa_inspect, text as sa_text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from starlette.middleware.sessions import SessionMiddleware


class Settings(BaseSettings):
    database_url: str = "sqlite:///./dev.db"
    app_secret_key: str = "development-only-change-me"
    initial_admin_username: str = "admin"
    initial_admin_password: str = "ChangeMeNow123!"
    storage_root: str = "./storage"
    max_upload_size_mb: int = 200
    session_ttl_hours: int = 8


settings = Settings()
storage_root = Path(settings.storage_root).resolve()
storage_root.mkdir(parents=True, exist_ok=True)
ph = PasswordHasher()
engine = create_engine(settings.database_url, pool_pre_ping=True,
                       connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name: Mapped[str] = mapped_column(String(200))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="member")
    status: Mapped[str] = mapped_column(String(20), default="active")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ProjectMember(Base):
    __tablename__ = "project_members"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    can_download: Mapped[bool] = mapped_column(Boolean, default=True)
    can_create_branches: Mapped[bool] = mapped_column(Boolean, default=False)


class Folder(Base):
    __tablename__ = "folders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    folder_id: Mapped[Optional[str]] = mapped_column(ForeignKey("folders.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    current_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class FileObject(Base):
    __tablename__ = "file_objects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Version(Base):
    __tablename__ = "document_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    file_object_id: Mapped[str] = mapped_column(ForeignKey("file_objects.id"))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str] = mapped_column(Text, default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    restored_from_id: Mapped[Optional[str]] = mapped_column(ForeignKey("document_versions.id"), nullable=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    branch_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    document_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details: Mapped[str] = mapped_column(Text, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    base_branch_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    base_json: Mapped[str] = mapped_column(Text, default="{}")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class BranchHead(Base):
    __tablename__ = "branch_heads"
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(36))


class Template(Base):
    __tablename__ = "templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200))
    paths: Mapped[str] = mapped_column(Text, default="[]")
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LoginPayload(BaseModel):
    username: str
    password: str


class ProjectPayload(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    description: str = ""
    template_id: Optional[str] = None


class FolderPayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: Optional[str] = None


class PasswordPayload(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)


app = FastAPI(title="DocFlow API", version="0.1.0", description="Локальное хранилище проектов и документов")
app.add_middleware(SessionMiddleware, secret_key=settings.app_secret_key, session_cookie="docflow_session",
                   max_age=settings.session_ttl_hours * 3600, same_site="lax", https_only=False)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost", "http://127.0.0.1"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def audit(db: Session, request: Request, event_type: str, user_id: Optional[str],
          project_id: Optional[str] = None, document_id: Optional[str] = None,
          version_id: Optional[str] = None, details: Optional[dict] = None):
    import json
    db.add(AuditEvent(event_type=event_type, user_id=user_id, project_id=project_id,
                      document_id=document_id, version_id=version_id,
                      ip_address=request.client.host if request.client else None,
                      details=json.dumps(details or {}, ensure_ascii=False)))


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(401, "Необходимо войти в систему")
    user = db.get(User, uid)
    if not user or user.status != "active":
        request.session.clear()
        raise HTTPException(401, "Сессия недействительна")
    return user


def require_admin(user: User):
    if user.role != "admin":
        raise HTTPException(403, "Недостаточно прав")


def project_access(db: Session, user: User, project_id: str, write: bool = False) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")
    if user.role == "admin":
        return project
    membership = db.get(ProjectMember, (project_id, user.id))
    if not membership:
        raise HTTPException(404, "Проект не найден")
    if write and (user.role == "observer" or membership.role == "observer"):
        raise HTTPException(403, "Недостаточно прав")
    return project


# ============================ Утилиты ============================
def iso(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def now():
    return datetime.now(timezone.utc)


def user_names(db: Session) -> dict:
    return {u.id: u.full_name for u in db.scalars(select(User)).all()}


def get_doc(db: Session, user: User, document_id: str, write: bool = False) -> Document:
    d = db.get(Document, document_id)
    if not d or d.status != "active":
        raise HTTPException(404, "Документ не найден")
    project_access(db, user, d.project_id, write=write)
    return d


def folder_path(db: Session, folder_id: Optional[str]) -> str:
    parts, seen = [], set()
    while folder_id and folder_id not in seen:
        seen.add(folder_id)
        f = db.get(Folder, folder_id)
        if not f:
            break
        parts.append(f.name)
        folder_id = f.parent_id
    return " / ".join(reversed(parts))


def require_manager(db: Session, user: User, project_id: str) -> Project:
    p = project_access(db, user, project_id)
    if user.role == "admin":
        return p
    m = db.get(ProjectMember, (project_id, user.id))
    if not m or m.role != "manager":
        raise HTTPException(403, "Управлять проектом может администратор или руководитель проекта")
    return p


# ============================ Ветки ============================
def default_branch(db: Session, project_id: str) -> Branch:
    b = db.scalar(select(Branch).where(Branch.project_id == project_id, Branch.is_default == True))  # noqa: E712
    if not b:
        b = Branch(project_id=project_id, name="main", is_default=True, base_json="{}")
        db.add(b)
        db.flush()
    return b


def resolve_branch(db: Session, project_id: str, branch_id: Optional[str]) -> Branch:
    if not branch_id:
        return default_branch(db, project_id)
    b = db.get(Branch, branch_id)
    if not b or b.project_id != project_id or b.status != "active":
        raise HTTPException(404, "Ветка не найдена")
    return b


def heads(db: Session, branch_id: str) -> dict:
    rows = db.scalars(select(BranchHead).where(BranchHead.branch_id == branch_id)).all()
    return {r.document_id: r.version_id for r in rows}


def set_head(db: Session, branch_id: str, document_id: str, version_id: str):
    h = db.get(BranchHead, (branch_id, document_id))
    if h:
        h.version_id = version_id
    else:
        db.add(BranchHead(branch_id=branch_id, document_id=document_id, version_id=version_id))


def drop_head(db: Session, branch_id: str, document_id: str):
    h = db.get(BranchHead, (branch_id, document_id))
    if h:
        db.delete(h)
    db.flush()
    left = db.scalar(select(func.count()).select_from(BranchHead).where(BranchHead.document_id == document_id))
    if not left:
        d = db.get(Document, document_id)
        if d:
            d.status = "deleted"
            d.deleted_at = now()


def store_bytes(db: Session, raw: bytes, mime: str) -> FileObject:
    oid = str(uuid.uuid4())
    rel = f"{oid[:2]}/{oid}.bin"
    dest = storage_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    obj = FileObject(storage_key=rel, sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw), mime_type=mime)
    db.add(obj)
    db.flush()
    return obj


def add_version(db: Session, doc: Document, branch_id: str, author_id: str, obj: FileObject, comment: str,
                restored_from: Optional[str] = None) -> Version:
    parent = heads(db, branch_id).get(doc.id)
    n = (db.scalar(select(func.max(Version.version_number)).where(Version.document_id == doc.id)) or 0) + 1
    v = Version(document_id=doc.id, version_number=n, file_object_id=obj.id, author_id=author_id, comment=comment,
                size_bytes=obj.size_bytes, mime_type=obj.mime_type, parent_id=parent, branch_id=branch_id,
                restored_from_id=restored_from)
    db.add(v)
    db.flush()
    set_head(db, branch_id, doc.id, v.id)
    doc.updated_at = now()
    return v


def sig(db: Session, version_id: Optional[str]) -> Optional[str]:
    if not version_id:
        return None
    v = db.get(Version, version_id)
    return db.get(FileObject, v.file_object_id).sha256 if v else None


def read_version(db: Session, version_id: str) -> bytes:
    v = db.get(Version, version_id)
    obj = db.get(FileObject, v.file_object_id)
    path = (storage_root / obj.storage_key).resolve()
    if storage_root not in path.parents or not path.is_file():
        raise HTTPException(500, "Файл недоступен в хранилище")
    return path.read_bytes()


# ============================ Текст и сравнение ============================
BINARY_EXT = {".pdf", ".xlsx", ".xls", ".pptx", ".ppt", ".doc", ".zip", ".rar", ".7z", ".png", ".jpg", ".jpeg",
              ".gif", ".bmp", ".tif", ".tiff", ".dwg", ".dxf", ".exe", ".bin", ".mp4", ".mp3"}


def decode_text(raw: bytes):
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def extract_text(name: str, raw: bytes):
    """-> (kind, text|None, encoding). kind: text | docx | binary"""
    ext = Path(name).suffix.lower()
    if ext in (".docx", ".docm"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                xml = z.read("word/document.xml").decode("utf-8")
            lines = []
            for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
                p = p.replace("<w:tab/>", "<w:t>\t</w:t>")
                lines.append("".join(htmllib.unescape(t) for t in re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", p, re.S)))
            return "docx", "\n".join(lines), "utf-8"
        except Exception:
            return "binary", None, ""
    if ext in BINARY_EXT or b"\0" in raw[:8192]:
        return "binary", None, ""
    text_, enc = decode_text(raw)
    return "text", text_, enc


def char_segments(x: str, y: str):
    if len(x) * len(y) > 4_000_000:
        return [[x, 1]], [[y, 1]]
    sm = SequenceMatcher(None, x, y, autojunk=False)
    if sm.ratio() < 0.3:
        return [[x, 1]], [[y, 1]]
    a, b = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            a.append([x[i1:i2], 0])
            b.append([y[j1:j2], 0])
        else:
            if i2 > i1:
                a.append([x[i1:i2], 1])
            if j2 > j1:
                b.append([y[j1:j2], 1])
    return a, b


def diff_rows(A: list, B: list, context: int = 3):
    rows = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, A, B, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append({"t": "eq", "an": i1 + k + 1, "bn": j1 + k + 1, "a": [[A[i1 + k], 0]]})
            continue
        n = min(i2 - i1, j2 - j1) if tag == "replace" else 0
        for k in range(n):
            sa, sb = char_segments(A[i1 + k], B[j1 + k])
            rows.append({"t": "chg", "an": i1 + k + 1, "bn": j1 + k + 1, "a": sa, "b": sb})
        for k in range(n, i2 - i1):
            rows.append({"t": "del", "an": i1 + k + 1, "a": [[A[i1 + k], 1]]})
        for k in range(n, j2 - j1):
            rows.append({"t": "add", "bn": j1 + k + 1, "b": [[B[j1 + k], 1]]})
    keep = [False] * len(rows)
    for i, r in enumerate(rows):
        if r["t"] != "eq":
            for j in range(max(0, i - context), min(len(rows), i + context + 1)):
                keep[j] = True
    out, skipped = [], 0
    for i, r in enumerate(rows):
        if keep[i]:
            if skipped:
                out.append({"t": "skip", "n": skipped})
                skipped = 0
            out.append(r)
        else:
            skipped += 1
    if skipped:
        out.append({"t": "skip", "n": skipped})
    stats = {"added_lines": sum(1 for r in rows if r["t"] in ("add", "chg")),
             "removed_lines": sum(1 for r in rows if r["t"] in ("del", "chg")),
             "added_chars": sum(len(s[0]) for r in rows for s in r.get("b", []) if s[1]),
             "removed_chars": sum(len(s[0]) for r in rows if r["t"] in ("del", "chg") for s in r.get("a", []) if s[1])}
    return out, stats


def merge3(base: list, a: list, b: list):
    """Трёхстороннее слияние по строкам. None — есть конфликт."""
    def changes(x, side):
        return [(i1, i2, x[j1:j2], side) for tag, i1, i2, j1, j2 in
                SequenceMatcher(None, base, x, autojunk=False).get_opcodes() if tag != "equal"]
    allc = sorted(changes(a, "a") + changes(b, "b"), key=lambda c: (c[0], c[1]))
    out, pos, last = [], 0, None
    for c in allc:
        if last and c[3] != last[3] and c[0] <= last[1]:
            if c[0] == last[0] and c[1] == last[1] and c[2] == last[2]:
                continue
            return None
        out += base[pos:c[0]] + c[2]
        pos = c[1]
        last = c
    return out + base[pos:]


def auto_merge(db: Session, base_id: str, src_id: str, dst_id: str, name: str):
    kinds = []
    for vid in (base_id, src_id, dst_id):
        kinds.append(extract_text(name, read_version(db, vid)))
    if any(k[0] != "text" for k in kinds):
        return None
    lines = [k[1].splitlines(keepends=True) for k in kinds]
    merged = merge3(lines[0], lines[1], lines[2])
    if merged is None:
        return None
    return "".join(merged).encode(kinds[2][2] if kinds[2][2] != "utf-8-sig" else "utf-8")


def plan_merge(db: Session, src: Branch, dst: Branch):
    base = json.loads(src.base_json or "{}")
    S, T = heads(db, src.id), heads(db, dst.id)
    items = []
    for did in set(S) | set(T) | set(base):
        s, t, b = S.get(did), T.get(did), base.get(did)
        ss, ts, bs = sig(db, s), sig(db, t), sig(db, b)
        if ss == ts or ss == bs:
            continue
        doc = db.get(Document, did)
        if not doc or doc.status != "active":
            continue
        item = {"document_id": did, "name": doc.name, "folder": folder_path(db, doc.folder_id),
                "source_version": s, "target_version": t, "base_version": b, "auto": False}
        if ts == bs:
            item["status"] = "removed" if s is None else ("added" if t is None else "modified")
        else:
            item["status"] = "conflict"
            if s and t and b:
                item["auto"] = auto_merge(db, b, s, t, doc.name) is not None
        items.append(item)
    items.sort(key=lambda i: (i["folder"], i["name"]))
    return items


# ============================ Старт и миграция ============================
def migrate():
    Base.metadata.create_all(engine)
    insp = sa_inspect(engine)

    def addcol(table, col, ddl):
        if col not in [c["name"] for c in insp.get_columns(table)]:
            with engine.begin() as c:
                c.execute(sa_text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))

    addcol("document_versions", "parent_id", "VARCHAR(36)")
    addcol("document_versions", "branch_id", "VARCHAR(36)")
    addcol("folders", "status", "VARCHAR(20) DEFAULT 'active'")
    with engine.begin() as c:
        c.execute(sa_text("UPDATE folders SET status='active' WHERE status IS NULL"))
    with SessionLocal() as db:
        for p in db.scalars(select(Project)).all():
            if db.scalar(select(Branch).where(Branch.project_id == p.id, Branch.is_default == True)):  # noqa: E712
                continue
            main = default_branch(db, p.id)
            for d in db.scalars(select(Document).where(Document.project_id == p.id, Document.status == "active")).all():
                if d.current_version_id:
                    set_head(db, main.id, d.id, d.current_version_id)
            for v in db.scalars(select(Version).join(Document, Document.id == Version.document_id)
                                .where(Document.project_id == p.id, Version.branch_id.is_(None))).all():
                v.branch_id = main.id
        db.commit()


@app.on_event("startup")
def startup():
    migrate()
    with SessionLocal() as db:
        username = settings.initial_admin_username
        if not db.scalar(select(User).where(User.username == username)):
            db.add(User(full_name="Системный администратор", username=username,
                        password_hash=ph.hash(settings.initial_admin_password), role="admin",
                        status="active", must_change_password=True))
            db.commit()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "docflow"}


@app.post("/api/auth/login")
def login(payload: LoginPayload, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    valid = False
    if user and user.status == "active":
        try:
            valid = ph.verify(user.password_hash, payload.password)
        except (VerifyMismatchError, Exception):
            valid = False
    if not valid:
        audit(db, request, "auth.login.failed", user.id if user else None, details={"username": payload.username})
        db.commit()
        raise HTTPException(401, "Неверный логин или пароль")
    request.session.clear()
    request.session["user_id"] = user.id
    user.last_login_at = datetime.now(timezone.utc)
    audit(db, request, "auth.login.success", user.id)
    db.commit()
    return {"id": user.id, "full_name": user.full_name, "username": user.username,
            "role": user.role, "must_change_password": user.must_change_password}


@app.post("/api/auth/logout")
def logout(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    audit(db, request, "auth.logout", user.id)
    db.commit()
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "full_name": user.full_name, "username": user.username,
            "email": user.email, "role": user.role, "must_change_password": user.must_change_password}


@app.post("/api/auth/change-password")
def change_password(payload: PasswordPayload, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    try:
        if not ph.verify(user.password_hash, payload.current_password):
            raise HTTPException(400, "Текущий пароль указан неверно")
    except VerifyMismatchError:
        raise HTTPException(400, "Текущий пароль указан неверно")
    if payload.new_password == payload.current_password:
        raise HTTPException(400, "Новый пароль должен отличаться от текущего")
    user.password_hash = ph.hash(payload.new_password)
    user.must_change_password = False
    audit(db, request, "auth.password_changed", user.id)
    db.commit()
    return {"ok": True}


# ============================ Пользователи ============================
ROLES = {"admin", "project_manager", "member", "observer"}


@app.get("/api/users")
def list_users(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(user)
    return [{"id": x.id, "full_name": x.full_name, "username": x.username, "email": x.email,
             "role": x.role, "status": x.status, "created_at": iso(x.created_at),
             "last_login_at": iso(x.last_login_at)} for x in db.scalars(select(User).order_by(User.full_name)).all()]


@app.get("/api/users/directory")
def users_directory(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in {"admin", "project_manager"}:
        raise HTTPException(403, "Недостаточно прав")
    return [{"id": x.id, "full_name": x.full_name, "username": x.username}
            for x in db.scalars(select(User).where(User.status == "active").order_by(User.full_name)).all()]


@app.post("/api/users")
def create_user(payload: dict, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(user)
    if any(not str(payload.get(k) or "").strip() for k in ["full_name", "username", "password", "role"]):
        raise HTTPException(422, "Заполните ФИО, логин, пароль и роль")
    if payload["role"] not in ROLES:
        raise HTTPException(422, "Недопустимая роль")
    if len(payload["password"]) < 12:
        raise HTTPException(422, "Пароль должен содержать не менее 12 символов")
    if db.scalar(select(User).where(User.username == payload["username"].strip())):
        raise HTTPException(409, "Такой логин уже существует")
    nu = User(full_name=payload["full_name"].strip(), username=payload["username"].strip(),
              email=(payload.get("email") or None), password_hash=ph.hash(payload["password"]),
              role=payload["role"], must_change_password=True)
    db.add(nu)
    audit(db, request, "user.created", user.id, details={"username": nu.username, "role": nu.role})
    db.commit()
    return {"id": nu.id, "username": nu.username}


@app.patch("/api/users/{user_id}")
def update_user(user_id: str, payload: dict, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    require_admin(user)
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Пользователь не найден")
    if "role" in payload:
        if payload["role"] not in ROLES:
            raise HTTPException(422, "Недопустимая роль")
        if u.id == user.id and payload["role"] != "admin":
            raise HTTPException(400, "Нельзя снять роль администратора с самого себя")
        u.role = payload["role"]
    if "status" in payload:
        if payload["status"] not in {"active", "blocked"}:
            raise HTTPException(422, "Недопустимый статус")
        if u.id == user.id and payload["status"] != "active":
            raise HTTPException(400, "Нельзя заблокировать самого себя")
        u.status = payload["status"]
    if payload.get("full_name"):
        u.full_name = payload["full_name"].strip()
    if "email" in payload:
        u.email = payload["email"] or None
    if payload.get("new_password"):
        if len(payload["new_password"]) < 12:
            raise HTTPException(422, "Пароль должен содержать не менее 12 символов")
        u.password_hash = ph.hash(payload["new_password"])
        u.must_change_password = u.id != user.id
    audit(db, request, "user.updated", user.id, details={"user": u.username, "fields": list(payload.keys())})
    db.commit()
    return {"ok": True}


# ============================ Проекты, шаблоны, участники ============================
def apply_paths(db: Session, project_id: str, user_id: str, paths: list):
    cache = {}
    for p in paths:
        parent, key = None, ()
        for part in [x.strip() for x in str(p).replace("\\", "/").split("/") if x.strip()]:
            key += (part,)
            if key not in cache:
                f = Folder(project_id=project_id, parent_id=parent, name=part[:255], owner_id=user_id)
                db.add(f)
                db.flush()
                cache[key] = f.id
            parent = cache[key]


@app.get("/api/templates")
def list_templates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "paths": json.loads(t.paths or "[]")}
            for t in db.scalars(select(Template).order_by(Template.name)).all()]


@app.post("/api/templates")
def create_template(payload: dict, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in {"admin", "project_manager"}:
        raise HTTPException(403, "Недостаточно прав")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "Укажите название шаблона")
    paths = payload.get("paths")
    if payload.get("from_project_id"):
        project_access(db, user, payload["from_project_id"])
        folders = db.scalars(select(Folder).where(Folder.project_id == payload["from_project_id"],
                                                  Folder.status == "active")).all()
        paths = [folder_path(db, f.id).replace(" / ", "/") for f in folders]
    paths = [str(p).strip() for p in (paths or []) if str(p).strip()]
    if not paths:
        raise HTTPException(422, "В шаблоне должна быть хотя бы одна папка")
    t = Template(name=name, paths=json.dumps(paths, ensure_ascii=False), created_by=user.id)
    db.add(t)
    audit(db, request, "template.created", user.id, details={"name": name})
    db.commit()
    return {"id": t.id}


@app.delete("/api/templates/{template_id}")
def delete_template(template_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in {"admin", "project_manager"}:
        raise HTTPException(403, "Недостаточно прав")
    t = db.get(Template, template_id)
    if t:
        db.delete(t)
        db.commit()
    return {"ok": True}


@app.get("/api/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "admin":
        projects = db.scalars(select(Project).order_by(Project.updated_at.desc())).all()
    else:
        ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        projects = db.scalars(select(Project).where(Project.id.in_(ids)).order_by(Project.updated_at.desc())).all()
    return [{"id": p.id, "name": p.name, "description": p.description, "status": p.status,
             "created_at": iso(p.created_at), "updated_at": iso(p.updated_at)} for p in projects]


@app.post("/api/projects")
def create_project(payload: ProjectPayload, request: Request, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    if user.role not in {"admin", "project_manager"}:
        raise HTTPException(403, "Создавать проекты может администратор или руководитель")
    p = Project(name=payload.name.strip(), description=payload.description, owner_id=user.id)
    db.add(p)
    db.flush()
    db.add(ProjectMember(project_id=p.id, user_id=user.id, role="manager", can_download=True, can_create_branches=True))
    default_branch(db, p.id)
    tpl = db.get(Template, payload.template_id) if payload.template_id else None
    if tpl:
        apply_paths(db, p.id, user.id, json.loads(tpl.paths or "[]"))
    else:
        db.add(Folder(project_id=p.id, parent_id=None, name="Корневая папка", owner_id=user.id))
    audit(db, request, "project.created", user.id, project_id=p.id,
          details={"name": p.name, "template": tpl.name if tpl else None})
    db.commit()
    return {"id": p.id, "name": p.name, "description": p.description, "status": p.status}


@app.get("/api/projects/{project_id}/members")
def list_members(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_access(db, user, project_id)
    rows = db.execute(select(ProjectMember, User).join(User, User.id == ProjectMember.user_id)
                      .where(ProjectMember.project_id == project_id)).all()
    return [{"user_id": u.id, "full_name": u.full_name, "username": u.username, "role": m.role} for m, u in rows]


@app.post("/api/projects/{project_id}/members")
def add_member(project_id: str, payload: dict, request: Request, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    require_manager(db, user, project_id)
    role = payload.get("role", "member")
    if role not in {"manager", "member", "observer"}:
        raise HTTPException(422, "Недопустимая роль")
    if not db.get(User, payload.get("user_id")):
        raise HTTPException(404, "Пользователь не найден")
    m = db.get(ProjectMember, (project_id, payload["user_id"]))
    if m:
        m.role = role
    else:
        db.add(ProjectMember(project_id=project_id, user_id=payload["user_id"], role=role,
                             can_download=True, can_create_branches=role != "observer"))
    audit(db, request, "member.added", user.id, project_id=project_id, details={"user_id": payload["user_id"], "role": role})
    db.commit()
    return {"ok": True}


@app.delete("/api/projects/{project_id}/members/{member_id}")
def remove_member(project_id: str, member_id: str, request: Request, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    require_manager(db, user, project_id)
    m = db.get(ProjectMember, (project_id, member_id))
    if m:
        db.delete(m)
        audit(db, request, "member.removed", user.id, project_id=project_id, details={"user_id": member_id})
        db.commit()
    return {"ok": True}


# ============================ Папки ============================
@app.get("/api/projects/{project_id}/tree")
def project_tree(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_access(db, user, project_id)
    folders = db.scalars(select(Folder).where(Folder.project_id == project_id, Folder.status == "active")
                         .order_by(Folder.name)).all()
    return [{"id": f.id, "project_id": f.project_id, "parent_id": f.parent_id, "name": f.name} for f in folders]


@app.post("/api/projects/{project_id}/folders")
def create_folder(project_id: str, payload: FolderPayload, request: Request,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_access(db, user, project_id, write=True)
    if payload.parent_id:
        parent = db.get(Folder, payload.parent_id)
        if not parent or parent.project_id != project_id or parent.status != "active":
            raise HTTPException(400, "Родительская папка не найдена")
    f = Folder(project_id=project_id, parent_id=payload.parent_id, name=payload.name.strip(), owner_id=user.id)
    db.add(f)
    audit(db, request, "folder.created", user.id, project_id=project_id, details={"name": f.name})
    db.commit()
    return {"id": f.id, "name": f.name, "parent_id": f.parent_id}


@app.patch("/api/folders/{folder_id}")
def rename_folder(folder_id: str, payload: dict, request: Request, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    f = db.get(Folder, folder_id)
    if not f or f.status != "active":
        raise HTTPException(404, "Папка не найдена")
    project_access(db, user, f.project_id, write=True)
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "Укажите название")
    audit(db, request, "folder.renamed", user.id, project_id=f.project_id, details={"from": f.name, "to": name})
    f.name = name[:255]
    db.commit()
    return {"ok": True}


@app.delete("/api/folders/{folder_id}")
def delete_folder(folder_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(Folder, folder_id)
    if not f or f.status != "active":
        raise HTTPException(404, "Папка не найдена")
    project_access(db, user, f.project_id, write=True)
    ids, stack = [], [f.id]
    while stack:
        cur = stack.pop()
        ids.append(cur)
        stack += [c.id for c in db.scalars(select(Folder).where(Folder.parent_id == cur, Folder.status == "active")).all()]
    count = 0
    for d in db.scalars(select(Document).where(Document.folder_id.in_(ids), Document.status == "active")).all():
        for h in db.scalars(select(BranchHead).where(BranchHead.document_id == d.id)).all():
            db.delete(h)
        d.status = "deleted"
        d.deleted_at = now()
        count += 1
    for fid in ids:
        db.get(Folder, fid).status = "deleted"
    audit(db, request, "folder.deleted", user.id, project_id=f.project_id,
          details={"name": f.name, "folders": len(ids), "documents": count})
    db.commit()
    return {"ok": True, "folders": len(ids), "documents": count}


# ============================ Ветки ============================
def branch_dict(db: Session, b: Branch, names: dict, dflt: Optional[Branch]):
    ahead = 0
    if dflt and b.id != dflt.id:
        ahead = len(plan_merge(db, b, dflt))
    return {"id": b.id, "name": b.name, "is_default": b.is_default, "created_at": iso(b.created_at),
            "created_by": names.get(b.created_by), "base_branch_id": b.base_branch_id, "changes_vs_main": ahead}


@app.get("/api/projects/{project_id}/branches")
def list_branches(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_access(db, user, project_id)
    dflt = default_branch(db, project_id)
    db.commit()
    names = user_names(db)
    rows = db.scalars(select(Branch).where(Branch.project_id == project_id, Branch.status == "active")
                      .order_by(Branch.is_default.desc(), Branch.created_at)).all()
    return [branch_dict(db, b, names, dflt) for b in rows]


@app.post("/api/projects/{project_id}/branches")
def create_branch(project_id: str, payload: dict, request: Request, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    project_access(db, user, project_id, write=True)
    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 100:
        raise HTTPException(422, "Укажите название ветки (до 100 символов)")
    if db.scalar(select(Branch).where(Branch.project_id == project_id, Branch.name == name, Branch.status == "active")):
        raise HTTPException(409, "Ветка с таким названием уже существует")
    src = resolve_branch(db, project_id, payload.get("from_branch_id"))
    snap = heads(db, src.id)
    b = Branch(project_id=project_id, name=name, base_branch_id=src.id, base_json=json.dumps(snap),
               created_by=user.id)
    db.add(b)
    db.flush()
    for did, vid in snap.items():
        db.add(BranchHead(branch_id=b.id, document_id=did, version_id=vid))
    audit(db, request, "branch.created", user.id, project_id=project_id, details={"name": name, "from": src.name})
    db.commit()
    return {"id": b.id, "name": b.name}


@app.delete("/api/branches/{branch_id}")
def delete_branch(branch_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(Branch, branch_id)
    if not b or b.status != "active":
        raise HTTPException(404, "Ветка не найдена")
    project_access(db, user, b.project_id, write=True)
    if b.is_default:
        raise HTTPException(400, "Основную ветку удалить нельзя")
    for h in db.scalars(select(BranchHead).where(BranchHead.branch_id == b.id)).all():
        db.delete(h)
    b.status = "deleted"
    db.flush()
    # документы, существовавшие только в удалённой ветке
    for d in db.scalars(select(Document).where(Document.project_id == b.project_id, Document.status == "active")).all():
        if not db.scalar(select(func.count()).select_from(BranchHead).where(BranchHead.document_id == d.id)):
            d.status = "deleted"
            d.deleted_at = now()
    audit(db, request, "branch.deleted", user.id, project_id=b.project_id, details={"name": b.name})
    db.commit()
    return {"ok": True}


@app.get("/api/branches/{branch_id}/compare")
def compare_branches(branch_id: str, target_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    src, dst = db.get(Branch, branch_id), db.get(Branch, target_id)
    if not src or not dst or src.project_id != dst.project_id:
        raise HTTPException(404, "Ветка не найдена")
    project_access(db, user, src.project_id)
    return {"source": src.name, "target": dst.name, "items": plan_merge(db, src, dst)}


@app.post("/api/branches/{branch_id}/merge")
def merge_branch(branch_id: str, payload: dict, request: Request, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    if not payload.get("target_id"):
        raise HTTPException(400, "Выберите ветку для слияния")
    src, dst = db.get(Branch, branch_id), db.get(Branch, payload["target_id"])
    if not src or not dst or src.project_id != dst.project_id or src.id == dst.id:
        raise HTTPException(400, "Выберите другую ветку для слияния")
    project_access(db, user, src.project_id, write=True)
    resolutions = payload.get("resolutions") or {}
    items = plan_merge(db, src, dst)
    unresolved = [i["name"] for i in items if i["status"] == "conflict" and not i["auto"] and i["document_id"] not in resolutions]
    if unresolved:
        raise HTTPException(409, "Не разрешены конфликты: " + ", ".join(unresolved))
    msg = f"Слияние «{src.name}» → «{dst.name}»" + (f": {payload['message']}" if payload.get("message") else "")
    applied = 0
    for it in items:
        doc = db.get(Document, it["document_id"])
        choice = resolutions.get(doc.id) or ("auto" if it["status"] == "conflict" else "source")
        if choice == "target":
            continue
        if choice == "auto":
            data = auto_merge(db, it["base_version"], it["source_version"], it["target_version"], doc.name)
            if data is None:
                raise HTTPException(409, f"Автослияние невозможно: {doc.name}")
            add_version(db, doc, dst.id, user.id, store_bytes(db, data, db.get(Version, it["target_version"]).mime_type), msg)
        elif it["source_version"] is None:
            drop_head(db, dst.id, doc.id)
        else:
            sv = db.get(Version, it["source_version"])
            add_version(db, doc, dst.id, user.id, db.get(FileObject, sv.file_object_id), msg, restored_from=sv.id)
        applied += 1
    src.base_json = json.dumps(heads(db, dst.id))
    audit(db, request, "branch.merged", user.id, project_id=src.project_id,
          details={"from": src.name, "to": dst.name, "documents": applied})
    db.commit()
    return {"ok": True, "applied": applied}


# ============================ Документы ============================
@app.get("/api/folders/{folder_id}/documents")
def list_documents(folder_id: str, branch_id: Optional[str] = None, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    folder = db.get(Folder, folder_id)
    if not folder or folder.status != "active":
        raise HTTPException(404, "Папка не найдена")
    project_access(db, user, folder.project_id)
    b = resolve_branch(db, folder.project_id, branch_id)
    rows = db.execute(select(Document, Version).join(BranchHead, BranchHead.document_id == Document.id)
                      .join(Version, Version.id == BranchHead.version_id)
                      .where(BranchHead.branch_id == b.id, Document.folder_id == folder_id,
                             Document.status == "active").order_by(Document.name)).all()
    names = user_names(db)
    return [{"id": d.id, "name": d.name, "description": d.description, "current_version": v.version_number,
             "version_id": v.id, "size_bytes": v.size_bytes, "author": names.get(v.author_id),
             "comment": v.comment, "updated_at": iso(v.created_at)} for d, v in rows]


@app.post("/api/folders/{folder_id}/documents")
async def upload_document(folder_id: str, request: Request, branch_id: Optional[str] = None,
                          file: UploadFile = File(...), description: str = Form(""), comment: str = Form(""),
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    folder = db.get(Folder, folder_id)
    if not folder or folder.status != "active":
        raise HTTPException(404, "Папка не найдена")
    project_access(db, user, folder.project_id, write=True)
    b = resolve_branch(db, folder.project_id, branch_id)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(413, f"Файл превышает лимит {settings.max_upload_size_mb} МБ")
    if not raw:
        raise HTTPException(400, "Пустой файл")
    name = Path(file.filename or "document.bin").name[:255]
    mime = file.content_type or "application/octet-stream"
    H = heads(db, b.id)
    existing = None
    for d in db.scalars(select(Document).where(Document.folder_id == folder_id, Document.name == name,
                                               Document.status == "active")).all():
        if d.id in H:
            existing = d
            break
    if existing:
        if sig(db, H[existing.id]) == hashlib.sha256(raw).hexdigest():
            return {"id": existing.id, "name": name, "unchanged": True,
                    "message": "Файл не отличается от текущей версии — новая версия не создана"}
        v = add_version(db, existing, b.id, user.id, store_bytes(db, raw, mime), comment or "Обновление файла")
        audit(db, request, "version.created", user.id, project_id=folder.project_id, document_id=existing.id,
              version_id=v.id, details={"name": name, "branch": b.name, "version": v.version_number})
        db.commit()
        return {"id": existing.id, "name": name, "updated": True, "version_number": v.version_number}
    doc = Document(project_id=folder.project_id, folder_id=folder.id, name=name, description=description,
                   owner_id=user.id, status="active")
    db.add(doc)
    db.flush()
    v = add_version(db, doc, b.id, user.id, store_bytes(db, raw, mime), comment or "Первоначальная загрузка")
    audit(db, request, "document.created", user.id, project_id=folder.project_id, document_id=doc.id,
          version_id=v.id, details={"name": name, "branch": b.name, "size_bytes": len(raw)})
    db.commit()
    return {"id": doc.id, "name": name, "created": True, "version_number": 1}


@app.get("/api/documents/{document_id}")
def get_document(document_id: str, branch_id: Optional[str] = None, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    d = get_doc(db, user, document_id)
    b = resolve_branch(db, d.project_id, branch_id)
    head = heads(db, b.id).get(d.id)
    names = user_names(db)
    bnames = {x.id: x.name for x in db.scalars(select(Branch).where(Branch.project_id == d.project_id)).all()}
    vs = db.scalars(select(Version).where(Version.document_id == d.id).order_by(Version.version_number.desc())).all()
    by_num = {v.version_number: v.id for v in vs}
    return {"id": d.id, "name": d.name, "description": d.description, "project_id": d.project_id,
            "folder_id": d.folder_id, "folder": folder_path(db, d.folder_id), "head_version_id": head,
            "branch": b.name,
            "versions": [{"id": v.id, "version_number": v.version_number, "comment": v.comment,
                          "size_bytes": v.size_bytes, "created_at": iso(v.created_at),
                          "author": names.get(v.author_id), "branch": bnames.get(v.branch_id),
                          "prev_id": v.parent_id or by_num.get(v.version_number - 1),
                          "is_head": v.id == head} for v in vs]}


@app.post("/api/documents/{document_id}/versions")
async def upload_version(document_id: str, request: Request, branch_id: Optional[str] = None,
                         file: UploadFile = File(...), comment: str = Form(""),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_doc(db, user, document_id, write=True)
    b = resolve_branch(db, d.project_id, branch_id)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(413, "Файл превышает допустимый размер")
    if not raw:
        raise HTTPException(400, "Пустой файл")
    head = heads(db, b.id).get(d.id)
    if head and sig(db, head) == hashlib.sha256(raw).hexdigest():
        return {"unchanged": True, "message": "Файл не отличается от текущей версии"}
    v = add_version(db, d, b.id, user.id, store_bytes(db, raw, file.content_type or "application/octet-stream"),
                    comment or "Новая версия")
    audit(db, request, "version.created", user.id, project_id=d.project_id, document_id=d.id, version_id=v.id,
          details={"name": d.name, "branch": b.name, "version": v.version_number})
    db.commit()
    return {"id": v.id, "version_number": v.version_number}


@app.get("/api/versions/{version_id}/download")
def download_version(version_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = db.get(Version, version_id)
    d = db.get(Document, v.document_id) if v else None
    if not d:
        raise HTTPException(404, "Версия не найдена")
    project_access(db, user, d.project_id)
    obj = db.get(FileObject, v.file_object_id)
    path = (storage_root / obj.storage_key).resolve()
    if storage_root not in path.parents or not path.is_file():
        raise HTTPException(500, "Файл недоступен в хранилище")
    audit(db, request, "document.downloaded", user.id, project_id=d.project_id, document_id=d.id, version_id=v.id)
    db.commit()
    return FileResponse(path, media_type=v.mime_type, filename=d.name)


@app.get("/api/versions/{version_id}/text")
def version_text(version_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = db.get(Version, version_id)
    d = db.get(Document, v.document_id) if v else None
    if not d:
        raise HTTPException(404, "Версия не найдена")
    project_access(db, user, d.project_id)
    kind, text_, _ = extract_text(d.name, read_version(db, v.id))
    if text_ is not None and len(text_) > 500_000:
        text_ = text_[:500_000] + "\n… (показано первые 500 000 символов)"
    return {"kind": kind, "text": text_, "name": d.name}


@app.get("/api/diff")
def diff_versions(a: Optional[str] = None, b: Optional[str] = None, full: bool = False,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    docs, raws = [], []
    for vid in (a, b):
        if vid:
            v = db.get(Version, vid)
            d = db.get(Document, v.document_id) if v else None
            if not d:
                raise HTTPException(404, "Версия не найдена")
            project_access(db, user, d.project_id)
            docs.append(d)
            raws.append((v, read_version(db, vid)))
        else:
            raws.append((None, b""))
    if not docs:
        raise HTTPException(400, "Не указаны версии")
    name = docs[-1].name
    ka, ta, _ = extract_text(name, raws[0][1]) if a else ("text", "", "")
    kb, tb, _ = extract_text(name, raws[1][1]) if b else ("text", "", "")
    if "binary" in (ka, kb):
        sa = hashlib.sha256(raws[0][1]).hexdigest() if a else None
        sb = hashlib.sha256(raws[1][1]).hexdigest() if b else None
        return {"kind": "binary", "same": sa == sb, "size_a": len(raws[0][1]), "size_b": len(raws[1][1])}
    A, B = (ta or "").splitlines(), (tb or "").splitlines()
    if len(A) + len(B) > 40000:
        return {"kind": "toolarge"}
    rows, stats = diff_rows(A, B, context=10**9 if full else 3)
    return {"kind": "docx" if "docx" in (ka, kb) else "text", "rows": rows, "stats": stats}


@app.post("/api/versions/{version_id}/restore")
def restore_version(version_id: str, request: Request, branch_id: Optional[str] = None,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    src = db.get(Version, version_id)
    d = db.get(Document, src.document_id) if src else None
    if not d or d.status != "active":
        raise HTTPException(404, "Версия не найдена")
    project_access(db, user, d.project_id, write=True)
    b = resolve_branch(db, d.project_id, branch_id)
    v = add_version(db, d, b.id, user.id, db.get(FileObject, src.file_object_id),
                    f"Восстановлено из версии {src.version_number}", restored_from=src.id)
    audit(db, request, "version.restored", user.id, project_id=d.project_id, document_id=d.id, version_id=v.id,
          details={"name": d.name, "from_version": src.version_number})
    db.commit()
    return {"id": v.id, "version_number": v.version_number}


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str, request: Request, branch_id: Optional[str] = None,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = get_doc(db, user, document_id, write=True)
    b = resolve_branch(db, d.project_id, branch_id)
    if d.id not in heads(db, b.id):
        raise HTTPException(404, "Документа нет в этой ветке")
    drop_head(db, b.id, d.id)
    audit(db, request, "document.deleted", user.id, project_id=d.project_id, document_id=d.id,
          details={"name": d.name, "branch": b.name})
    db.commit()
    return {"ok": True}


# ============================ История ============================
EVENT_TYPES = ("document.deleted", "folder.created", "folder.deleted", "folder.renamed", "branch.created",
               "branch.deleted", "branch.merged", "project.created", "member.added", "member.removed")


@app.get("/api/history")
def history(project_id: Optional[str] = None, branch_id: Optional[str] = None, document_id: Optional[str] = None,
            limit: int = 200, user: User = Depends(current_user), db: Session = Depends(get_db)):
    limit = max(1, min(limit, 500))
    if project_id:
        project_access(db, user, project_id)
        pids = [project_id]
    elif user.role == "admin":
        pids = [p.id for p in db.scalars(select(Project)).all()]
    else:
        pids = [m.project_id for m in db.scalars(select(ProjectMember).where(ProjectMember.user_id == user.id)).all()]
    names = user_names(db)
    pnames = {p.id: p.name for p in db.scalars(select(Project).where(Project.id.in_(pids))).all()} if pids else {}
    bnames = {b.id: b.name for b in db.scalars(select(Branch).where(Branch.project_id.in_(pids))).all()} if pids else {}
    q = select(Version, Document).join(Document, Document.id == Version.document_id).where(Document.project_id.in_(pids))
    if branch_id:
        q = q.where(Version.branch_id == branch_id)
    if document_id:
        q = q.where(Version.document_id == document_id)
    items = []
    for v, d in db.execute(q.order_by(Version.created_at.desc()).limit(limit)).all():
        by_prev = v.parent_id or db.scalar(select(Version.id).where(Version.document_id == d.id,
                                                                    Version.version_number == v.version_number - 1))
        items.append({"kind": "version", "id": v.id, "at": iso(v.created_at), "project": pnames.get(d.project_id),
                      "document_id": d.id, "name": d.name, "folder": folder_path(db, d.folder_id),
                      "version_number": v.version_number, "comment": v.comment, "author": names.get(v.author_id),
                      "branch": bnames.get(v.branch_id), "prev_id": by_prev, "size_bytes": v.size_bytes})
    if not branch_id:
        eq = select(AuditEvent).where(AuditEvent.project_id.in_(pids), AuditEvent.event_type.in_(EVENT_TYPES))
        if document_id:
            eq = eq.where(AuditEvent.document_id == document_id)
        for e in db.scalars(eq.order_by(AuditEvent.occurred_at.desc()).limit(limit)).all():
            try:
                det = json.loads(e.details or "{}")
            except Exception:
                det = {}
            items.append({"kind": "event", "type": e.event_type, "at": iso(e.occurred_at),
                          "project": pnames.get(e.project_id), "author": names.get(e.user_id), "details": det})
    items.sort(key=lambda i: i["at"] or "", reverse=True)
    return items[:limit]


@app.get("/api/audit-events")
def list_audit_events(user: User = Depends(current_user), db: Session = Depends(get_db), limit: int = 100):
    require_admin(user)
    limit = max(1, min(limit, 500))
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)).all()
    return [{"id": e.id, "event_type": e.event_type, "project_id": e.project_id, "document_id": e.document_id,
             "user_id": e.user_id, "ip_address": e.ip_address, "details": e.details,
             "occurred_at": iso(e.occurred_at)} for e in rows]


# ---- Раздача собранного фронтенда (для запуска без Docker/Nginx) ----
from fastapi.responses import HTMLResponse  # noqa: E402

_dist = Path(os.environ.get("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    if _dist.is_dir():
        target = (_dist / full_path).resolve()
        if full_path and target.is_file() and _dist.resolve() in target.parents:
            return FileResponse(target)
        index = _dist / "index.html"
        if index.is_file():
            return FileResponse(index)
    return HTMLResponse(
        "<h2>DocFlow API работает</h2><p>Интерфейс не собран (нужен Node.js 18+). "
        "Установите Node.js и перезапустите start.bat, либо используйте "
        "<a href='/api/docs'>/api/docs</a>.</p>", status_code=200)
