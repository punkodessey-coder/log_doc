"""DocFlow для Windows: python run.py [IP] [PORT]
Ставит библиотеки, при необходимости скачивает Node.js и собирает интерфейс, запускает сервер."""
import json, os, secrets, shutil, socket, subprocess, sys, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
NODE_VER = "v22.11.0"
NODE_DIR = ROOT / ".tools" / f"node-{NODE_VER}-win-x64"


def run(cmd, **kw):
    print(">", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True, **kw)


def install_deps():
    req = ROOT / "backend" / "requirements.txt"
    stamp = DATA / ".deps_ok"
    if stamp.exists() and stamp.stat().st_mtime >= req.stat().st_mtime:
        return
    run([sys.executable, "-m", "pip", "install", "-r", str(req)])
    stamp.write_text("ok")


def find_npm():
    npm = shutil.which("npm")
    if npm:
        return npm, os.environ.copy()
    if os.name != "nt":
        return None, None
    if not NODE_DIR.exists():
        url = f"https://nodejs.org/dist/{NODE_VER}/node-{NODE_VER}-win-x64.zip"
        print("Node.js не найден, скачиваю портативную версию (~30 МБ)...")
        z = ROOT / ".tools" / "node.zip"
        z.parent.mkdir(exist_ok=True)
        urllib.request.urlretrieve(url, z)
        with zipfile.ZipFile(z) as f:
            f.extractall(ROOT / ".tools")
        z.unlink()
    env = os.environ.copy()
    env["PATH"] = str(NODE_DIR) + os.pathsep + env["PATH"]
    return str(NODE_DIR / "npm.cmd"), env


def build_frontend():
    fe = ROOT / "frontend"
    idx = fe / "dist" / "index.html"
    if idx.exists() and all(f.stat().st_mtime <= idx.stat().st_mtime
                            for f in list((fe / "src").glob("*")) + [fe / "package.json"]):
        return
    try:
        npm, env = find_npm()
        if not npm:
            raise RuntimeError("Node.js не найден")
        run([npm, "install", "--no-audit", "--no-fund"], cwd=fe, env=env)
        run([npm, "run", "build"], cwd=fe, env=env)
    except Exception as e:
        print(f"\nНе удалось собрать интерфейс: {e}\nДоступен только API: /api/docs\n")


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    if sys.version_info[:2] != (3, 12):
        print(f"ВНИМАНИЕ: рекомендуется Python 3.12, сейчас {sys.version.split()[0]}")
    host = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    (DATA / "storage").mkdir(parents=True, exist_ok=True)
    install_deps()
    build_frontend()
    cfg_file = DATA / "config.json"
    if not cfg_file.exists():
        cfg_file.write_text(json.dumps({"app_secret_key": secrets.token_urlsafe(48),
                                        "admin_password": secrets.token_urlsafe(12) + "A1!"}, indent=2))
    cfg = json.loads(cfg_file.read_text())
    os.environ.setdefault("DATABASE_URL", "sqlite:///" + (DATA / "docflow.db").as_posix())
    os.environ.setdefault("STORAGE_ROOT", str(DATA / "storage"))
    os.environ.setdefault("APP_SECRET_KEY", cfg["app_secret_key"])
    os.environ.setdefault("INITIAL_ADMIN_PASSWORD", cfg["admin_password"])
    shown = lan_ip() if host in ("0.0.0.0", "::") else host
    print("\n" + "=" * 60)
    print(f" DocFlow: http://{shown}:{port}   (API: /api/docs)")
    print(f" Логин: admin   Пароль: {cfg['admin_password']}")
    print(f" Пароль также в {cfg_file}; смените его после входа")
    print("=" * 60 + "\n")
    import uvicorn
    uvicorn.run("app.main:app", host=host, port=port, app_dir=str(ROOT / "backend"))


if __name__ == "__main__":
    main()
