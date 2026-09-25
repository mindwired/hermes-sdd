#!/usr/bin/env python3
"""Build deterministic source archives after repository verification."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "release", "build"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
FIXED_EPOCH = 315532800  # 1980-01-01, ZIP's minimum timestamp.


def files() -> list[Path]:
    status = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if any(line[0] != "?" and line[1] != "?" for line in status.splitlines()):
        raise RuntimeError("Cannot build a release with tracked working tree changes")
    result: list[Path] = []
    tracked = set(
        subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if path.is_symlink() and rel.as_posix() in tracked:
            raise RuntimeError(f"Cannot include tracked symlinked files in release archives: {rel}")
        if path.is_file() and path.suffix not in EXCLUDED_SUFFIXES and rel.as_posix() in tracked:
            result.append(path)
    return sorted(result, key=lambda p: p.relative_to(ROOT).as_posix())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_zip(output: Path, prefix: str) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in files():
            rel = source.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(f"{prefix}/{rel}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if os.access(source, os.X_OK) else 0o644) << 16
            archive.writestr(
                info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
            )


def add_tar(output: Path, prefix: str) -> None:
    with output.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for source in files():
                    rel = source.relative_to(ROOT).as_posix()
                    info = archive.gettarinfo(str(source), arcname=f"{prefix}/{rel}")
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = FIXED_EPOCH
                    with source.open("rb") as handle:
                        archive.addfile(info, handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "release")
    args = parser.parse_args()

    expected = {}
    exec((ROOT / "hermes_sdd" / "version.py").read_text(encoding="utf-8"), expected)
    if args.version != expected["__version__"]:
        raise SystemExit(
            f"Requested version {args.version} != source version {expected['__version__']}"
        )

    with tempfile.TemporaryDirectory(prefix="hermes-sdd-verify-") as temp:
        env = dict(os.environ)
        env["PYTHONPYCACHEPREFIX"] = temp
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify.py"), "--require-node"],
            cwd=ROOT,
            env=env,
        )
    if result.returncode:
        return result.returncode

    if args.output.is_symlink():
        raise RuntimeError(f"Release output cannot be a symlink: {args.output}")
    requested_output = Path(os.path.abspath(args.output.expanduser()))
    if requested_output == ROOT or ROOT.is_relative_to(requested_output):
        raise RuntimeError("Release output cannot be the repository root or its parent")
    output = requested_output.resolve()
    if requested_output != output:
        raise RuntimeError(f"Release output cannot traverse a symlink: {requested_output}")
    try:
        relative_output = output.relative_to(ROOT)
    except ValueError:
        relative_output = None
    if relative_output is not None and relative_output != Path("release"):
        raise RuntimeError(
            "Release output inside the repository must use the managed 'release' directory"
        )
    if output.exists() and not output.is_dir():
        raise RuntimeError(f"Release output is not a directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    prefix = f"hermes-sdd-{args.version}"
    if relative_output is not None:
        managed_artifact = re.compile(
            r"^hermes-sdd-[A-Za-z0-9][A-Za-z0-9._+-]*\.(?:zip|tar\.gz)(?:\.sha256)?$"
        )
        symlinks = sorted(path.name for path in output.iterdir() if path.is_symlink())
        if symlinks:
            raise RuntimeError(
                f"Managed release directory contains symlinks: {', '.join(symlinks)}"
            )
        expected_artifacts = {
            f"{prefix}.zip",
            f"{prefix}.tar.gz",
            f"{prefix}.zip.sha256",
            f"{prefix}.tar.gz.sha256",
        }
        entries = list(output.iterdir())
        invalid_entries = sorted(path.name for path in entries if not path.is_file())
        if invalid_entries:
            raise RuntimeError(
                f"Managed release directory contains non-file entries: {', '.join(invalid_entries)}"
            )
        stale = sorted(
            path.name
            for path in entries
            if managed_artifact.fullmatch(path.name) and path.name not in expected_artifacts
        )
        if stale:
            raise RuntimeError(
                f"Managed release directory contains stale release artifacts: {', '.join(stale)}"
            )
        unexpected = sorted(
            path.name
            for path in entries
            if path.name not in expected_artifacts and path.name not in stale
        )
        if unexpected:
            raise RuntimeError(
                f"Managed release directory contains unexpected files: {', '.join(unexpected)}"
            )
    zip_path = output / f"{prefix}.zip"
    tar_path = output / f"{prefix}.tar.gz"
    checksum_paths = [
        archive.with_suffix(archive.suffix + ".sha256") for archive in (zip_path, tar_path)
    ]
    symlink_targets = sorted(
        path.name for path in (zip_path, tar_path, *checksum_paths) if path.is_symlink()
    )
    if symlink_targets:
        raise RuntimeError(f"Refusing symlinked release output files: {', '.join(symlink_targets)}")
    add_zip(zip_path, prefix)
    add_tar(tar_path, prefix)
    for archive in (zip_path, tar_path):
        (archive.with_suffix(archive.suffix + ".sha256")).write_text(
            f"{sha256(archive)}  {archive.name}\n", encoding="utf-8"
        )
        print(f"{archive}  sha256={sha256(archive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
