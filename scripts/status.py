import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def matches_process(record, process):
    try:
        marker = Path(record["marker"]).resolve()
        if marker != ROOT / "scripts" / "boot_astrbot.py":
            return False
        return (
            abs(process.create_time() - record["create_time"]) < 0.01
            and os.path.normcase(process.exe()) == os.path.normcase(record["exe"])
            and str(marker).casefold()
            in [str(Path(arg)).casefold() for arg in process.cmdline()]
        )
    except Exception:
        return False


def running(root=ROOT):
    import psutil

    path = Path(root) / "runtime" / "state" / "process.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        process = psutil.Process(record["pid"])
        return process if matches_process(record, process) else None
    except (OSError, ValueError, KeyError, psutil.Error):
        return None


def request(method, path, root=ROOT, body=None):
    secret = json.loads(
        (Path(root) / "config" / "secrets.local.json").read_text(encoding="utf-8-sig")
    )
    data = (
        json.dumps(body).encode("utf-8")
        if body is not None
        else (b"{}" if method == "POST" else None)
    )
    req = urllib.request.Request(
        "http://127.0.0.1:6185" + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + secret["control_token"],
            "Content-Type": "application/json",
        },
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        req, timeout=3
    ) as response:
        return json.load(response)


def stop(root=ROOT):
    process = running(root)
    try:
        request("POST", "/stop", root)
    except Exception:
        if not process:
            return "未发现本项目的运行进程。"
    if process:
        import psutil

        try:
            process.wait(timeout=35)
        except psutil.TimeoutExpired:
            # Re-read and verify all identity fields immediately before termination.
            verified = running(root)
            if verified and verified.pid == process.pid:
                verified.terminate()
                verified.wait(timeout=10)
    return "满穗已停止。"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--retry", type=int)
    parser.add_argument("--ready", action="store_true")
    args = parser.parse_args()
    if args.check:
        return 0 if running() else 1
    if args.ready:
        try:
            return 0 if request("GET", "/status").get("service") == "ready" else 1
        except Exception:
            return 1
    if args.stop:
        print(stop())
        return 0
    try:
        data = (
            request("POST", "/retry", body={"seq": args.retry})
            if args.retry
            else request("GET", "/status")
        )
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        print("满穗尚未运行，或本机配置未完成。请先查看 README 与「配置满穗」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
