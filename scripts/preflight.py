import argparse
import hashlib
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plugins.mansui_companion.settings import load_settings


def port_available(port):
    with socket.socket() as sock:
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def check(root=ROOT, offline=False):
    root = Path(root)
    problems = []
    for name in (
        "app/AstrBot/main.py",
        "app/NapCat/napcat.mjs",
        "runtime/venv/Scripts/python.exe",
        "config/versions.lock.json",
    ):
        if not (root / name).is_file():
            problems.append("missing:" + name)
    source = root / "plugins" / "mansui_companion"
    copy = root / "data" / "astrbot" / "data" / "plugins" / "mansui_companion"
    for path in source.glob("*"):
        if path.is_file():
            target = copy / path.name
            if (
                not target.exists()
                or hashlib.sha256(path.read_bytes()).digest()
                != hashlib.sha256(target.read_bytes()).digest()
            ):
                problems.append("plugin_copy_mismatch:" + path.name)
    for path in (root, root / "runtime", root / "config", root / "data"):
        if path.exists() and (path.is_symlink() or path.is_junction()):
            problems.append("reparse_root_refused")
    if not offline:
        try:
            cfg = load_settings(
                root / "config" / "mansui.local.json",
                root / "config" / "secrets.local.json",
            )
            if not all((cfg.deepseek_api_key, cfg.onebot_token, cfg.control_token)):
                problems.append("credentials_missing")
        except Exception:
            problems.append("configuration_missing_or_invalid")
        for port in (6185, 6199, 6099):
            if not port_available(port):
                problems.append("port_in_use:" + str(port))
        try:
            lock = json.loads(
                (root / "config" / "versions.lock.json").read_text(encoding="utf-8-sig")
            )
            launch = lock.get("qq_launch", {})
            if not launch.get("verified") or not launch.get("approved_data_paths"):
                problems.append("qq_session_path_not_verified")
            elif not Path(launch["executable"]).is_file():
                problems.append("qq_executable_missing")
        except Exception:
            problems.append("version_lock_invalid")
    return problems


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    issues = check(offline=args.offline)
    print("\n".join(issues) if issues else "preflight_ok")
    sys.exit(bool(issues))
