from __future__ import annotations

import hashlib
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
engine = create_engine(settings.database_url, pool_pre_ping=True)
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


class LoginPayload(BaseModel):
    username: str
    password: str


class ProjectPayload(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    description: str = ""


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


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        username = settings.initial_admin_username
        admin = db.scalar(select(User).where(User.username == username))
        if not admin:
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


@app.get("/api/users")
def list_users(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(user)
    users = db.scalars(select(User).order_by(User.full_name)).all()
    return [{"id": x.id, "full_name": x.full_name, "username": x.username, "email": x.email,
             "role": x.role, "status": x.status, "created_at": x.created_at,
             "last_login_at": x.last_login_at} for x in users]


@app.post("/api/users")
def create_user(payload: dict, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(user)
    required = ["full_name", "username", "password", "role"]
    if any(not payload.get(k) for k in required):
        raise HTTPException(422, "Заполните ФИО, логин, пароль и роль")
    if payload["role"] not in {"admin", "project_manager", "member", "observer"}:
        raise HTTPException(422, "Недопустимая роль")
    if len(payload["password"]) < 12:
        raise HTTPException(422, "Стартовый пароль должен содержать не менее 12 символов")
    if db.scalar(select(User).where(User.username == payload["username"])):
        raise HTTPException(409, "Такой логин уже существует")
    new_user = User(full_name=payload["full_name"], username=payload["username"],
                    email=payload.get("email"), password_hash=ph.hash(payload["password"]),
                    role=payload["role"], must_change_password=True)
    db.add(new_user)
    audit(db, request, "user.created", user.id, details={"username": payload["username"], "role": payload["role"]})
    db.commit()
    return {"id": new_user.id, "username": new_user.username}


@app.get("/api/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "admin":
        projects = db.scalars(select(Project).order_by(Project.updated_at.desc())).all()
    else:
        ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        projects = db.scalars(select(Project).where(Project.id.in_(ids)).order_by(Project.updated_at.desc())).all()
    return [{"id": p.id, "name": p.name, "description": p.description, "status": p.status,
             "created_at": p.created_at, "updated_at": p.updated_at} for p in projects]


@app.post("/api/projects")
def create_project(payload: ProjectPayload, request: Request, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    if user.role not in {"admin", "project_manager"}:
        raise HTTPException(403, "Создавать проекты может администратор или руководитель")
    p = Project(name=payload.name.strip(), description=payload.description, owner_id=user.id)
    db.add(p)
    db.flush()
    db.add(ProjectMember(project_id=p.id, user_id=user.id, role="manager", can_download=True, can_create_branches=True))
    db.add(Folder(project_id=p.id, parent_id=None, name="Корневая папка", owner_id=user.id))
    audit(db, request, "project.created", user.id, project_id=p.id, details={"name": p.name})
    db.commit()
    return {"id": p.id, "name": p.name, "description": p.description, "status": p.status}


@app.get("/api/projects/{project_id}/tree")
def project_tree(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_access(db, user, project_id)
    folders = db.scalars(select(Folder).where(Folder.project_id == project_id).order_by(Folder.name)).all()
    return [{"id": f.id, "project_id": f.project_id, "parent_id": f.parent_id, "name": f.name} for f in folders]


@app.post("/api/projects/{project_id}/folders")
def create_folder(project_id: str, payload: FolderPayload, request: Request,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_access(db, user, project_id, write=True)
    if payload.parent_id:
        parent = db.get(Folder, payload.parent_id)
        if not parent or parent.project_id != project_id:
            raise HTTPException(400, "Родительская папка относится к другому проекту")
    f = Folder(project_id=project_id, parent_id=payload.parent_id, name=payload.name.strip(), owner_id=user.id)
    db.add(f)
    audit(db, request, "folder.created", user.id, project_id=project_id, details={"name": f.name, "parent_id": f.parent_id})
    db.commit()
    return {"id": f.id, "name": f.name, "parent_id": f.parent_id}


@app.get("/api/folders/{folder_id}/documents")
def list_documents(folder_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    folder = db.get(Folder, folder_id)
    if not folder:
        raise HTTPException(404, "Папка не найдена")
    project_access(db, user, folder.project_id)
    docs = db.scalars(select(Document).where(Document.folder_id == folder_id, Document.status == "active")
                      .order_by(Document.updated_at.desc())).all()
    result = []
    for d in docs:
        v = db.get(Version, d.current_version_id) if d.current_version_id else None
        result.append({"id": d.id, "name": d.name, "description": d.description,
                       "current_version": v.version_number if v else None, "updated_at": d.updated_at})
    return result


@app.post("/api/folders/{folder_id}/documents")
async def upload_document(folder_id: str, request: Request, file: UploadFile = File(...),
                          description: str = Form(""), comment: str = Form("Первоначальная загрузка"),
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    folder = db.get(Folder, folder_id)
    if not folder:
        raise HTTPException(404, "Папка не найдена")
    project_access(db, user, folder.project_id, write=True)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(413, f"Файл превышает лимит {settings.max_upload_size_mb} МБ")
    if not raw:
        raise HTTPException(400, "Пустой файл")
    safe_name = Path(file.filename or "document.bin").name[:255]
    object_id = str(uuid.uuid4())
    rel = f"{object_id[:2]}/{object_id}.bin"
    dest = storage_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    checksum = hashlib.sha256(raw).hexdigest()
    mime = file.content_type or "application/octet-stream"
    obj = FileObject(storage_key=rel, sha256=checksum, size_bytes=len(raw), mime_type=mime)
    doc = Document(project_id=folder.project_id, folder_id=folder.id, name=safe_name,
                   description=description, owner_id=user.id, status="active")
    db.add_all([obj, doc])
    db.flush()
    version = Version(document_id=doc.id, version_number=1, file_object_id=obj.id, author_id=user.id,
                      comment=comment, size_bytes=len(raw), mime_type=mime)
    db.add(version)
    db.flush()
    doc.current_version_id = version.id
    doc.updated_at = datetime.now(timezone.utc)
    audit(db, request, "document.created", user.id, project_id=folder.project_id,
          document_id=doc.id, version_id=version.id, details={"name": safe_name, "size_bytes": len(raw)})
    db.commit()
    return {"id": doc.id, "name": doc.name, "version_number": 1, "size_bytes": len(raw)}


@app.get("/api/documents/{document_id}")
def get_document(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d or d.status != "active":
        raise HTTPException(404, "Документ не найден")
    project_access(db, user, d.project_id)
    versions = db.scalars(select(Version).where(Version.document_id == d.id).order_by(Version.version_number.desc())).all()
    current = db.get(Version, d.current_version_id) if d.current_version_id else None
    return {"id": d.id, "name": d.name, "description": d.description, "project_id": d.project_id,
            "folder_id": d.folder_id, "current_version": current.version_number if current else None,
            "versions": [{"id": v.id, "version_number": v.version_number, "comment": v.comment,
                          "size_bytes": v.size_bytes, "mime_type": v.mime_type, "created_at": v.created_at}
                         for v in versions]}


@app.post("/api/documents/{document_id}/versions")
async def upload_version(document_id: str, request: Request, file: UploadFile = File(...),
                         comment: str = Form(""), user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d or d.status != "active":
        raise HTTPException(404, "Документ не найден")
    project_access(db, user, d.project_id, write=True)
    raw = await file.read(settings.max_upload_size_mb * 1024 * 1024 + 1)
    if len(raw) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(413, "Файл превышает допустимый размер")
    if not raw:
        raise HTTPException(400, "Пустой файл")
    previous = db.scalar(select(func.max(Version.version_number)).where(Version.document_id == d.id)) or 0
    object_id = str(uuid.uuid4())
    rel = f"{object_id[:2]}/{object_id}.bin"
    dest = storage_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    mime = file.content_type or "application/octet-stream"
    obj = FileObject(storage_key=rel, sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw), mime_type=mime)
    db.add(obj)
    db.flush()
    v = Version(document_id=d.id, version_number=previous + 1, file_object_id=obj.id, author_id=user.id,
                comment=comment, size_bytes=len(raw), mime_type=mime)
    db.add(v)
    db.flush()
    d.current_version_id = v.id
    d.updated_at = datetime.now(timezone.utc)
    audit(db, request, "version.created", user.id, project_id=d.project_id, document_id=d.id,
          version_id=v.id, details={"version_number": v.version_number, "size_bytes": len(raw)})
    db.commit()
    return {"id": v.id, "version_number": v.version_number}


@app.get("/api/versions/{version_id}/download")
def download_version(version_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = db.get(Version, version_id)
    if not v:
        raise HTTPException(404, "Версия не найдена")
    d = db.get(Document, v.document_id)
    if not d:
        raise HTTPException(404, "Документ не найден")
    project_access(db, user, d.project_id)
    obj = db.get(FileObject, v.file_object_id)
    path = (storage_root / obj.storage_key).resolve()
    if storage_root not in path.parents or not path.is_file():
        raise HTTPException(500, "Файл недоступен в хранилище")
    audit(db, request, "document.downloaded", user.id, project_id=d.project_id,
          document_id=d.id, version_id=v.id, details={"version_number": v.version_number})
    db.commit()
    return FileResponse(path, media_type=v.mime_type, filename=d.name)


@app.post("/api/versions/{version_id}/restore")
def restore_version(version_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    source = db.get(Version, version_id)
    if not source:
        raise HTTPException(404, "Версия не найдена")
    d = db.get(Document, source.document_id)
    project_access(db, user, d.project_id, write=True)
    previous = db.scalar(select(func.max(Version.version_number)).where(Version.document_id == d.id)) or 0
    v = Version(document_id=d.id, version_number=previous + 1, file_object_id=source.file_object_id,
                author_id=user.id, comment=f"Восстановлено из версии {source.version_number}",
                size_bytes=source.size_bytes, mime_type=source.mime_type, restored_from_id=source.id)
    db.add(v)
    db.flush()
    d.current_version_id = v.id
    d.updated_at = datetime.now(timezone.utc)
    audit(db, request, "version.restored", user.id, project_id=d.project_id, document_id=d.id,
          version_id=v.id, details={"restored_from_version": source.version_number, "new_version": v.version_number})
    db.commit()
    return {"id": v.id, "version_number": v.version_number, "restored_from": source.version_number}


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d or d.status == "deleted":
        raise HTTPException(404, "Документ не найден")
    project_access(db, user, d.project_id, write=True)
    d.status = "deleted"
    d.deleted_at = datetime.now(timezone.utc)
    audit(db, request, "document.deleted", user.id, project_id=d.project_id, document_id=d.id,
          details={"name": d.name})
    db.commit()
    return {"ok": True}


@app.get("/api/audit-events")
def list_audit_events(user: User = Depends(current_user), db: Session = Depends(get_db), limit: int = 100):
    if user.role != "admin":
        raise HTTPException(403, "Журнал всех проектов доступен только администратору")
    limit = max(1, min(limit, 500))
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)).all()
    return [{"id": e.id, "event_type": e.event_type, "project_id": e.project_id,
             "document_id": e.document_id, "user_id": e.user_id, "ip_address": e.ip_address,
             "details": e.details, "occurred_at": e.occurred_at} for e in rows]


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
