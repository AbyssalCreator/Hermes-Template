#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import uvicorn
except Exception:
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    import uvicorn


def _writable_fallback(*candidates: str) -> Path:
    for candidate in candidates:
        path = Path(candidate)
        try:
            path.mkdir(parents=True, exist_ok=True)
            test = path / ".write_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink()
            return path
        except Exception:
            continue
    return Path.home() / "hermes"


HOME_ROOT = Path.home()
DATA_DIR = Path(os.environ.get("DATA_DIR") or str(_writable_fallback("/home/container/data", "/tmp/hermes-data", str(HOME_ROOT / "data"))))
HERMES_ROOT = Path(os.environ.get("HERMES_ROOT") or str(_writable_fallback("/home/container/hermes", "/tmp/hermes", str(HOME_ROOT / "hermes"))))
HERMES_HOME = Path(os.environ.get("HERMES_HOME") or str(_writable_fallback("/home/container/.hermes", "/tmp/.hermes", str(HOME_ROOT / ".hermes"))))
DEFAULT_HERMES_REF = os.environ.get("HERMES_REF", "v0.22.2")
HERMES_REPO_ROOT = HERMES_ROOT / "repo"
HERMES_RUNTIME_DIR = HERMES_ROOT / "tools"
HERMES_TUI_DIR = HERMES_ROOT / "ui-tui"


def log(msg: str) -> None:
    print(f"[main] {msg}", flush=True)


def run(cmd, *, cwd=None, env=None, check=True, capture=False):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        text=True,
        capture_output=capture,
        check=check,
    )


def ensure_python_requirements() -> None:
    req_file = REPO_DIR / "requirements.txt"
    if not req_file.exists():
        log("requirements.txt not found; skipping dependency install.")
        return

    log("Installing Python requirements...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], check=False)
    run([sys.executable, "-m", "pip", "install", "-r", str(req_file)], check=True)


def ensure_git() -> None:
    if shutil.which("git") is None:
        raise RuntimeError("git is required but not available in the current environment.")


def ensure_hermes_repo() -> None:
    hermes_root = HERMES_ROOT
    hermes_repo = HERMES_REPO_ROOT
    hermes_ref = os.environ.get("HERMES_REF", DEFAULT_HERMES_REF)

    try:
        hermes_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        fallback = _writable_fallback(str(Path.home() / "hermes"))
        os.environ["HERMES_ROOT"] = str(fallback)
        global HERMES_ROOT, HERMES_REPO_ROOT, HERMES_RUNTIME_DIR, HERMES_TUI_DIR
        HERMES_ROOT = fallback
        HERMES_REPO_ROOT = HERMES_ROOT / "repo"
        HERMES_RUNTIME_DIR = HERMES_ROOT / "tools"
        HERMES_TUI_DIR = HERMES_ROOT / "ui-tui"
        hermes_root = HERMES_ROOT
        hermes_repo = HERMES_REPO_ROOT
        log(f"Falling back to writable Hermes root: {hermes_root}")
        hermes_root.mkdir(parents=True, exist_ok=True)

    if not hermes_repo.exists():
        log(f"Cloning Hermes Agent {hermes_ref} into {hermes_repo}...")
        try:
            run([
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                hermes_ref,
                "https://github.com/NousResearch/hermes-agent.git",
                str(hermes_repo),
            ], check=True)
            return
        except Exception:
            log(f"Hermes clone failed for {hermes_ref}; continuing without upstream runtime bootstrap.")
            return

    if shutil.which("git") is not None:
        try:
            current = run(["git", "-C", str(hermes_repo), "rev-parse", "--abbrev-ref", "HEAD"], capture=True, check=False)
            if current.returncode == 0 and current.stdout.strip() != hermes_ref:
                log(f"Hermes repo exists but is on a different ref; fetching {hermes_ref}...")
                run(["git", "-C", str(hermes_repo), "fetch", "--depth", "1", "origin", hermes_ref], check=False)
                run(["git", "-C", str(hermes_repo), "checkout", hermes_ref], check=False)
        except Exception:
            pass


def ensure_hermes_home_layout() -> None:
    try:
        HERMES_HOME.mkdir(parents=True, exist_ok=True)
    except OSError:
        fallback = _writable_fallback(str(Path.home() / ".hermes"), "/tmp/.hermes")
        os.environ["HERMES_HOME"] = str(fallback)
        global HERMES_HOME
        HERMES_HOME = fallback
        HERMES_HOME.mkdir(parents=True, exist_ok=True)

    for rel in [
        "cron",
        "sessions",
        "logs",
        "memories",
        "skills",
        "platforms/pairing",
        "hooks",
        "cache/images",
        "cache/audio",
        "workspace",
        "skins",
        "plans",
        "home",
    ]:
        (HERMES_HOME / rel).mkdir(parents=True, exist_ok=True)

    (HERMES_HOME / ".install_method").write_text("docker\n", encoding="utf-8")

    auth_bootstrap = os.environ.get("HERMES_AUTH_JSON_BOOTSTRAP")
    auth_path = HERMES_HOME / "auth.json"
    if auth_bootstrap and not auth_path.exists():
        auth_path.write_text(auth_bootstrap, encoding="utf-8")
        try:
            auth_path.chmod(0o600)
        except OSError:
            pass

    for stale in [
        HERMES_HOME / "gateway.pid",
        HERMES_HOME / "gateway.lock",
        HERMES_HOME / "gateway.sock",
    ]:
        try:
            stale.unlink()
        except FileNotFoundError:
            pass


def set_hermes_env() -> None:
    os.environ.setdefault("PORT", "8080")
    os.environ.setdefault("HOST", "0.0.0.0")
    os.environ.setdefault("ADMIN_USERNAME", "admin")
    os.environ.setdefault("HOME", str(DATA_DIR))
    os.environ.setdefault("DATA_DIR", str(DATA_DIR))
    os.environ.setdefault("HERMES_ROOT", str(HERMES_ROOT))
    os.environ.setdefault("HERMES_HOME", str(HERMES_HOME))
    os.environ.setdefault("HERMES_REPO_ROOT", str(HERMES_REPO_ROOT))
    os.environ.setdefault("HERMES_RUNTIME_DIR", str(HERMES_RUNTIME_DIR))
    os.environ.setdefault("HERMES_TUI_DIR", str(HERMES_TUI_DIR))
    os.environ.setdefault("LD_LIBRARY_PATH", "/usr/local/lib")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    os.environ.setdefault("PATH", f"{HERMES_ROOT / 'bin'}:{HERMES_ROOT / 'wrapper-venv' / 'bin'}:" + os.environ.get("PATH", ""))

    if not os.environ.get("ADMIN_PASSWORD"):
        import secrets
        os.environ["ADMIN_PASSWORD"] = secrets.token_urlsafe(16)
        log(f"Generated ADMIN_PASSWORD={os.environ['ADMIN_PASSWORD']}")


def build_hermes_runtime() -> None:
    hermes_repo = HERMES_REPO_ROOT
    if not hermes_repo.exists():
        ensure_hermes_repo()

    build_script = hermes_repo / "build_hermes_image.py"
    if not build_script.exists():
        log("Hermes runtime build script not present in cloned repo; skipping native runtime assembly.")
        return

    log("Building Hermes runtime components (tools / dependencies / frontends / assemble)...")
    for target in ["tools", "dependencies", "frontends", "assemble", "verify"]:
        cmd = [sys.executable, str(build_script), target]
        log(f"Running: {' '.join(cmd)}")
        proc = run(cmd, cwd=str(hermes_repo), check=False, capture=True)
        if proc.stdout:
            print(proc.stdout, flush=True)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr, flush=True)
        if proc.returncode not in (0, 2):
            raise RuntimeError(f"build_hermes_image.py {target} exited with status {proc.returncode}")


def run_prepare_hermes() -> None:
    script = REPO_DIR / "prepare_hermes.py"
    if not script.exists():
        log("prepare_hermes.py not found in current repo; skipping logger preparation.")
        return

    log("Running Hermes configuration preparation...")
    proc = run([sys.executable, str(script)], cwd=str(REPO_DIR), check=False, capture=True)
    if proc.stdout:
        print(proc.stdout, flush=True)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, flush=True)
    if proc.returncode not in (0, 2):
        raise RuntimeError(f"prepare_hermes.py exited with {proc.returncode}")


def get_server_app():
    try:
        import server as srv
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Could not import server.py: {exc}") from exc

    app = getattr(srv, "app", None) or getattr(srv, "application", None)
    if app is None:
        raise RuntimeError("server.py does not expose an ASGI app at 'app' or 'application'.")
    return app


REPO_DIR = Path(__file__).resolve().parent


def main() -> None:
    set_hermes_env()
    ensure_git()
    ensure_python_requirements()
    ensure_hermes_repo()
    build_hermes_runtime()
    ensure_hermes_home_layout()
    run_prepare_hermes()

    app = get_server_app()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    log(f"Starting Hermes admin server on {host}:{port}...")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Shutting down cleanly.")
        raise SystemExit(0)
