import argparse
import os
import time
import zipfile
from datetime import datetime
from pathlib import Path


def confined_path(root, candidate):
    root = Path(root).absolute()
    resolved = root.resolve(strict=True)
    candidate = Path(candidate).absolute()
    if candidate.resolve() == resolved or not candidate.resolve().is_relative_to(
        resolved
    ):
        raise ValueError("outside_project_root")
    for part in [root, *candidate.parents, candidate]:
        if part.exists() and (part.is_symlink() or part.is_junction()):
            raise ValueError("reparse_path_refused")
    return candidate.resolve()


def cleanup(root, now=None):
    root = Path(root)
    now = time.time() if now is None else now
    # Only project media caches; login/session folders are never traversed.
    for rel in ("data/napcat/cache", "data/astrbot/data/temp"):
        directory = confined_path(root, root / rel)
        if not directory.exists():
            continue
        for parent, dirs, files in os.walk(directory, followlinks=False):
            for name in list(dirs):
                confined_path(root, Path(parent) / name)
            for name in files:
                path = confined_path(root, Path(parent) / name)
                if path.stat().st_mtime < now - 7 * 86400:
                    path.unlink()
    logs = root / "logs"
    if logs.exists():
        files = [confined_path(root, p) for p in logs.glob("*.log*") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        for path in sorted(files, key=lambda p: p.stat().st_mtime):
            if total <= 50 * 1024 * 1024:
                break
            size = path.stat().st_size
            path.unlink()
            total -= size


def backup(root):
    root = Path(root)
    target = confined_path(root, root / "backups")
    target.mkdir(parents=True, exist_ok=True)
    path = target / ("settings-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".zip")
    whitelist = (
        "config/mansui.example.json",
        "config/versions.lock.json",
        "plugins/mansui_companion/persona.md",
        "plugins/mansui_companion/persona-sources.md",
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in whitelist:
            source = confined_path(root, root / rel)
            if source.is_file():
                archive.write(source, rel)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.backup:
        print(backup(root))
    else:
        cleanup(root)
        print("项目缓存维护完成。")
