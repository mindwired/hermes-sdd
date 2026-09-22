"""Portable storage primitives for project-local SDD state."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_REMOTE_TERMINAL_BACKENDS = {
    "docker",
    "singularity",
    "modal",
    "managed_modal",
    "daytona",
    "vercel_sandbox",
    "ssh",
}


def _terminal_backend() -> str:
    return os.getenv("TERMINAL_ENV", "local").strip().lower() or "local"


def _pid_is_alive(pid: int) -> bool:
    """Check a lock owner's liveness without sending a signal on Windows."""
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.WaitForSingleObject.restype = ctypes.c_uint
            kernel32.GetLastError.restype = ctypes.c_uint
            handle = kernel32.OpenProcess(0x1000 | 0x100000, False, pid)
            if not handle:
                return kernel32.GetLastError() == 5
            try:
                return kernel32.WaitForSingleObject(handle, 0) == 0x102
            finally:
                kernel32.CloseHandle(handle)
        except (AttributeError, OSError):
            return True
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists():
        try:
            state = stat_path.read_text(encoding="utf-8").rsplit(")", 1)[1].strip().split(" ", 1)[0]
            if state == "Z":
                return False
        except (OSError, IndexError):
            pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_root(root: str | os.PathLike[str] | None, *, create: bool = False) -> Path:
    explicit = root is not None and str(root).strip() != ""
    if not explicit:
        backend = _terminal_backend()
        if backend in _REMOTE_TERMINAL_BACKENDS:
            raise ValueError(
                f"Remote terminal backend {backend!r} requires an explicit project root; "
                "pass root=<path> (or CLI --root/-C)"
            )
    raw = str(root) if explicit else (os.getenv("TERMINAL_CWD") or os.getcwd())
    path = Path(raw).expanduser().resolve()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists() or not path.is_dir():
        raise ValueError(f"Project root is not a directory: {path}")
    return path


def validate_id(value: str, label: str = "identifier") -> str:
    value = str(value or "").strip()
    if not _ID_RE.fullmatch(value):
        raise ValueError(
            f"Invalid {label} {value!r}; use 1-80 letters, digits, dots, underscores, or hyphens"
        )
    return value


def ensure_within(base: Path, candidate: Path) -> Path:
    base = base.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {candidate}") from exc
    return candidate


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Malformed SDD JSON object at {path}: expected a JSON object")
    return value


def ensure_no_symlinks(base: Path) -> None:
    """Reject links anywhere below canonical project metadata."""
    if base.is_symlink():
        raise ValueError(f"Refusing symlinked SDD path: {base}")
    if not base.exists():
        return
    for path in base.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Refusing symlinked SDD path: {path}")


def atomic_write_bytes(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise ValueError(f"Refusing symlinked SDD file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str) -> None:
    atomic_write_bytes(path, content.encode("utf-8"))


@contextlib.contextmanager
def project_transaction(sdd_dir: Path) -> Iterator[None]:
    """Rollback project-local metadata if a multi-file mutation fails.

    The project lock serializes writers, but it cannot undo an evidence append followed by a
    later state/render failure. This bounded snapshot covers only `.sdd` metadata and excludes
    the lock/cache implementation directories.
    """
    ensure_no_symlinks(sdd_dir)
    excluded = {sdd_dir / ".locks", sdd_dir / "cache"}
    snapshot: dict[Path, bytes] = {}
    for path in sdd_dir.rglob("*"):
        if not path.is_file() or any(parent in excluded for parent in path.parents):
            continue
        snapshot[path] = path.read_bytes()
    try:
        yield
    except Exception:
        current = [
            path
            for path in sdd_dir.rglob("*")
            if path.is_file() and not any(parent in excluded for parent in path.parents)
        ]
        for path in current:
            if path not in snapshot:
                path.unlink(missing_ok=True)
        ensure_no_symlinks(sdd_dir)
        for path, content in snapshot.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(path, content)
        raise


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    if path.is_symlink():
        raise ValueError(f"Refusing symlinked SDD file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink():
        raise ValueError(f"Refusing symlinked SDD file: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed SDD JSONL at {path}:{line_number}: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(
                    f"Malformed SDD JSONL at {path}:{line_number}: expected a JSON object"
                )
            rows.append(value)
    return rows[-limit:] if limit else rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@contextlib.contextmanager
def project_lock(
    sdd_dir: Path, *, timeout: float = 8.0, stale_after: float = 180.0
) -> Iterator[None]:
    """Cross-platform lock based on atomic file creation.

    It is intentionally short-lived and only protects metadata writes. Source-code edits are
    still coordinated by task file scopes and Hermes itself.
    """

    lock_dir = sdd_dir / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "state.lock"
    deadline = time.monotonic() + timeout

    def owner_is_alive() -> bool:
        try:
            metadata = json.loads(lock_path.read_text(encoding="utf-8"))
            pid = metadata.get("pid")
            if not isinstance(pid, int) or pid <= 0:
                return True
            return _pid_is_alive(pid)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return True

    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"pid": os.getpid(), "created_at": time.time()}))
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > stale_after and not owner_is_alive():
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for SDD lock: {lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)
