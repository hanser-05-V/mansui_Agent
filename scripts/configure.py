import argparse
import getpass
import json
import os
import secrets
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plugins.mansui_companion.settings import Settings


def framework_config(cfg):
    return {
        "config_version": 5,
        "provider": [],
        "provider_sources": [],
        "provider_settings": {"enable": False, "web_search": False},
        "trace_enable": False,
        "log_file_enable": False,
        "log_level": "WARNING",
        "disable_builtin_commands": True,
        "disable_metrics": True,
        "admins_id": [cfg.owner_qq],
        "plugin_set": ["mansui_companion"],
        "wake_prefix": [],
        "platform_settings": {
            "enable_id_white_list": False,
            "id_whitelist_log": False,
            "no_permission_reply": False,
            "empty_mention_waiting": False,
            "empty_mention_waiting_need_reply": False,
            "ignore_bot_self_message": True,
            "ignore_at_all": True,
            "rate_limit": {"time": 0, "count": 0, "strategy": "stall"},
        },
        "dashboard": {"enable": False, "host": "127.0.0.1", "port": 6185},
        "platform": [
            {
                "id": "mansui_onebot",
                "type": "aiocqhttp",
                "enable": True,
                "ws_reverse_host": "127.0.0.1",
                "ws_reverse_port": 6199,
                "ws_reverse_token": cfg.onebot_token,
            }
        ],
    }


def napcat_config(cfg):
    return {
        "network": {
            "httpServers": [],
            "httpClients": [],
            "websocketServers": [],
            "websocketClients": [
                {
                    "name": "mansui",
                    "enable": True,
                    "url": "ws://127.0.0.1:6199/ws",
                    "messagePostFormat": "array",
                    "reportSelfMessage": False,
                    "token": cfg.onebot_token,
                    "debug": False,
                    "reconnectInterval": 3000,
                    "heartInterval": 30000,
                }
            ],
        },
        "musicSignUrl": "",
        "enableLocalFile2Url": False,
        "parseMultMsg": False,
    }


def write_private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.is_junction():
        raise ValueError("reparse_file_refused")
    # The parent ACL is restricted before secret-bearing files are created.
    if os.name == "nt":
        identity = subprocess.check_output(["whoami"], text=True).strip()
        result = subprocess.run(
            [
                "icacls",
                str(path.parent),
                "/inheritance:r",
                "/grant:r",
                identity + ":(OI)(CI)F",
            ],
            capture_output=True,
        )
        if result.returncode:
            raise RuntimeError("private_acl_failed")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def save_configuration(root, cfg):
    root = Path(root).resolve()
    if root != ROOT and not root.is_relative_to(ROOT / "runtime" / "test-state"):
        raise ValueError("configuration_root_refused")
    values = asdict(cfg)
    secret = {
        k: values.pop(k) for k in ("deepseek_api_key", "onebot_token", "control_token")
    }
    values["allowed_groups"] = list(cfg.allowed_groups)
    write_private_json(root / "config" / "secrets.local.json", secret)
    write_private_json(root / "config" / "mansui.local.json", values)
    write_private_json(
        root / "data" / "astrbot" / "data" / "cmd_config.json", framework_config(cfg)
    )
    napcat = root / "data" / "napcat" / "config"
    write_private_json(
        napcat / "napcat.json",
        {
            "fileLog": False,
            "consoleLog": False,
            "fileLogLevel": "error",
            "consoleLogLevel": "error",
        },
    )
    write_private_json(
        napcat / ("onebot11_" + cfg.bot_qq + ".json"), napcat_config(cfg)
    )
    write_private_json(
        napcat / "webui.json",
        {"host": "127.0.0.1", "port": 6099, "token": cfg.control_token, "loginRate": 3},
    )


def main():
    parser = argparse.ArgumentParser(description="满穗本机配置；密钥输入不回显")
    parser.add_argument("--manage-memory", action="store_true")
    args = parser.parse_args()
    if args.manage_memory:
        from plugins.mansui_companion.store import Store
        from plugins.mansui_companion.memory import Memory
        from plugins.mansui_companion.settings import load_settings
        from plugins.mansui_companion.domain import Message
        from scripts.status import request

        try:
            request("GET", "/status")
            print("请先停止满穗，再管理群记忆。")
            return
        except Exception:
            pass
        cfg = load_settings(ROOT / "config" / "mansui.local.json")
        group = input("要管理的已启用群号：").strip()
        if group not in cfg.allowed_groups:
            raise ValueError("group_not_allowed")
        subject = input("目标成员 QQ：").strip()
        scope = Message(cfg.bot_qq, subject, group, "", "", "", 0).scope
        store = Store(ROOT / "data" / "mansui.sqlite3")
        try:
            memory = Memory(store)
            for row in memory.list(scope, subject):
                print(row["id"], row["kind"], row["text"])
            command = input("输入 遗忘 编号 或 纠正 编号 新文本（回车退出）：").split(
                maxsplit=2
            )
            if command and command[0] == "遗忘":
                memory.forget(scope, subject, int(command[1]))
            elif command and command[0] == "纠正":
                memory.correct(scope, subject, int(command[1]), command[2])
        finally:
            store.close()
        return
    print("资料将写入 E:\\QQAgent。此步骤保存真实账号配置；请在批准接入阶段后进行。")
    local = ROOT / "config" / "mansui.local.json"
    sec = ROOT / "config" / "secrets.local.json"
    values = (
        json.loads(local.read_text(encoding="utf-8-sig"))
        if local.exists()
        else json.loads(
            (ROOT / "config" / "mansui.example.json").read_text(encoding="utf-8-sig")
        )
    )
    previous = json.loads(sec.read_text(encoding="utf-8-sig")) if sec.exists() else {}
    for field, label in (("owner_qq", "你的 QQ"), ("bot_qq", "机器人小号 QQ")):
        entered = input(
            f"{label}（当前 {values.get(field) or '未设置'}，回车保留）："
        ).strip()
        if entered:
            values[field] = entered
    entered = input("允许群号，以逗号分隔；回车保留，输入 - 清空：").strip()
    if entered:
        values["allowed_groups"] = (
            []
            if entered == "-"
            else [s.strip() for s in entered.replace("，", ",").split(",") if s.strip()]
        )
    key = getpass.getpass(
        "DeepSeek API Key（输入不回显，回车保留）："
    ).strip() or previous.get("deepseek_api_key", "")
    if not key:
        raise ValueError("api_key_required")
    values["ready"] = True
    secret = {
        "deepseek_api_key": key,
        "onebot_token": previous.get("onebot_token") or secrets.token_urlsafe(32),
        "control_token": previous.get("control_token") or secrets.token_urlsafe(32),
    }
    cfg = Settings.from_dict(values, secret)
    print(
        f"本人 {cfg.owner_qq}；小号 {cfg.bot_qq}；启用群 {', '.join(cfg.allowed_groups) or '无'}；目录 {ROOT}"
    )
    if input("确认保存这些本机配置？输入 保存：").strip() != "保存":
        print("未保存。")
        return
    save_configuration(ROOT, cfg)
    print("配置已保存，未调用模型、未登录 QQ。")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(
            "配置未完成：" + str(exc)
            if isinstance(exc, (ValueError, RuntimeError))
            else "配置文件缺失。"
        )
        sys.exit(1)
