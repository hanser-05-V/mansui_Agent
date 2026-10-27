import argparse
import asyncio
import hashlib
import json
import logging
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class SingleInstance:
    def __init__(self, root):
        self.handle = None
        if os.name == "nt":
            import win32api, win32event, winerror

            name = (
                "Local\\QQAgentCore-"
                + hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:20]
            )
            self.handle = win32event.CreateMutex(None, False, name)
            if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
                self.handle.Close()
                self.handle = None
                raise RuntimeError("already_running")

    def close(self):
        if self.handle:
            self.handle.Close()
            self.handle = None


def launch_owned(executable, arguments, environment, cwd):
    import win32job, win32process

    job = win32job.CreateJobObject(None, "")
    limits = win32job.QueryInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation
    )
    limits["BasicLimitInformation"]["LimitFlags"] |= (
        win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    win32job.SetInformationJobObject(
        job, win32job.JobObjectExtendedLimitInformation, limits
    )
    command = subprocess.list2cmdline([str(executable), *map(str, arguments)])
    process, thread, pid, tid = win32process.CreateProcess(
        str(executable),
        command,
        None,
        None,
        False,
        win32process.CREATE_SUSPENDED | win32process.CREATE_NO_WINDOW,
        environment,
        str(cwd),
        win32process.STARTUPINFO(),
    )
    try:
        win32job.AssignProcessToJobObject(job, process)
        win32process.ResumeThread(thread)
    except Exception:
        win32process.TerminateProcess(process, 1)
        job.Close()
        raise
    finally:
        thread.Close()
        process.Close()
    return job, pid


async def control_app(token, stop_event, snapshot, retry=None):
    from aiohttp import web

    @web.middleware
    async def authentication(request, handler):
        if request.remote not in ("127.0.0.1", "::1") or not secrets.compare_digest(
            request.headers.get("Authorization", ""), "Bearer " + token
        ):
            raise web.HTTPUnauthorized()
        return await handler(request)

    app = web.Application(middlewares=[authentication], client_max_size=2048)

    async def status(request):
        return web.json_response(await snapshot())

    async def stop(request):
        stop_event.set()
        return web.json_response({"status": "stopping"})

    async def retry_handler(request):
        if retry is None:
            raise web.HTTPConflict()
        try:
            data = await request.json()
            result = retry(data["seq"])
            return web.json_response({"status": result})
        except (ValueError, KeyError, TypeError):
            raise web.HTTPBadRequest() from None

    app.router.add_get("/status", status)
    app.router.add_post("/stop", stop)
    app.router.add_post("/retry", retry_handler)
    return app


async def run(root, smoke=False, port=6185):
    from aiohttp import web
    import psutil
    from plugins.mansui_companion.settings import load_settings
    from scripts import ingress_guard

    cfg = load_settings(
        root / "config" / "mansui.local.json", root / "config" / "secrets.local.json"
    )
    lock = SingleInstance(root)
    runner = None
    core = None
    job = None
    task = None
    stop_event = asyncio.Event()
    state = root / "runtime" / "state"
    state.mkdir(parents=True, exist_ok=True)
    record_path = state / "process.json"
    process = psutil.Process()
    record = {
        "pid": process.pid,
        "create_time": process.create_time(),
        "exe": process.exe(),
        "marker": str(ROOT / "scripts" / "boot_astrbot.py"),
        "root": str(root),
    }
    record_path.write_text(json.dumps(record), encoding="utf-8")
    try:
        if not smoke:
            sys.path.insert(0, str(ROOT / "app" / "AstrBot"))
            sys.path.insert(0, str(root / "data" / "astrbot"))
            from astrbot.core import db_helper, LogBroker
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )
            from astrbot.core import core_lifecycle

            async def no_metadata_fetch():
                return None

            core_lifecycle.update_llm_metadata = no_metadata_fetch
            ingress_guard.install_guard(AiocqhttpAdapter, cfg)
            # Disable raw framework logging including broker sinks; own status uses codes only.
            from loguru import logger

            logger.disable("")
            logging.disable(logging.CRITICAL)
            core = core_lifecycle.AstrBotCoreLifecycle(LogBroker(), db_helper)
            await core.initialize()
            if not ingress_guard.is_ready():
                raise RuntimeError("plugin_not_ready")
            task = asyncio.create_task(core.start())

        async def snapshot():
            plugin = ingress_guard.plugin
            info = {
                "service": "ready"
                if smoke or ingress_guard.is_ready()
                else "not_ready",
                "qq_login": "unknown",
                "onebot_connected": False,
                "model_key_present": bool(cfg.deepseek_api_key),
                "memory_mb": round(process.memory_info().rss / 1024**2, 1),
            }
            if core:
                adapter = next(
                    (
                        p
                        for p in core.platform_manager.platform_insts
                        if p.meta().id == "mansui_onebot"
                    ),
                    None,
                )
                if adapter:
                    clients = getattr(adapter.bot, "_wsr_api_clients", {})
                    info["onebot_connected"] = cfg.bot_qq in [str(k) for k in clients]
                    if info["onebot_connected"]:
                        try:
                            status = await asyncio.wait_for(
                                adapter.bot.call_action("get_login_info"), 2
                            )
                            info["qq_login"] = (
                                "verified"
                                if str(status.get("user_id")) == cfg.bot_qq
                                else "account_mismatch"
                            )
                        except Exception:
                            info["qq_login"] = "check_failed"
                if plugin and plugin.store:
                    info.update(
                        queues={
                            k: len(v)
                            for k, v in plugin.service.scheduler.queues.items()
                        },
                        pending=plugin.store.pending(),
                        day=plugin.usage.summary(),
                        month=plugin.usage.summary("month"),
                        status_codes=[
                            dict(r)
                            for r in plugin.store.db.execute(
                                "SELECT * FROM local_status WHERE name NOT LIKE 'summary_seq:%'"
                            )
                        ],
                    )
            return info

        def retry(seq):
            if type(seq) is not int or not ingress_guard.is_ready():
                raise ValueError()
            from plugins.mansui_companion.domain import Message, Route

            plugin = ingress_guard.plugin
            row = plugin.store.db.execute(
                "SELECT e.*,m.content FROM events e JOIN messages m ON e.seq=m.event_seq AND m.role='user' WHERE e.seq=?",
                (seq,),
            ).fetchone()
            if not row or row["state"] not in (
                "awaiting_retry",
                "overloaded",
                "failed",
            ):
                return "retry_not_safe"
            message = Message(
                row["bot"],
                row["sender"],
                row["group_id"],
                row["message_id"],
                row["content"],
                frozenset(),
                __import__("time").time(),
            )
            result = plugin.service.scheduler.submit(message, Route(row["route"]))
            if result == "queued":
                plugin.store.transition(
                    message.key, row["state"], "queued", "manual_retry"
                )
            return result

        runner = web.AppRunner(
            await control_app(cfg.control_token, stop_event, snapshot, retry),
            access_log=None,
        )
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", port).start()
        if not smoke:
            # Launch details are populated only after the separately approved QQ compatibility check.
            versions = json.loads(
                (root / "config" / "versions.lock.json").read_text(encoding="utf-8-sig")
            )
            launch = versions.get("qq_launch", {})
            if not launch.get("verified") or not launch.get("approved_data_paths"):
                raise RuntimeError("qq_session_path_not_verified")
            env = dict(os.environ)
            env.update(
                NAPCAT_PATCH_PACKAGE=str(root / "app" / "NapCat" / "qqnt.json"),
                NAPCAT_LOAD_PATH=str(root / "app" / "NapCat" / "loadNapCat.js"),
                NAPCAT_MAIN_PATH=str(root / "app" / "NapCat" / "napcat.mjs"),
            )
            job, _ = launch_owned(
                root / "app" / "NapCat" / "NapCatWinBootMain.exe",
                [
                    launch["executable"],
                    str(root / "app" / "NapCat" / "NapCatWinBootHook.dll"),
                    *launch.get("arguments", []),
                ],
                env,
                root / "app" / "NapCat",
            )
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), 30)
            except TimeoutError:
                if core and task.done():
                    raise RuntimeError("framework_stopped")
                if ingress_guard.plugin and ingress_guard.plugin.store:
                    ingress_guard.plugin.store.prune_raw(days=cfg.raw_retention_days)
                    from scripts.maintenance import cleanup

                    cleanup(root)
    finally:
        if ingress_guard.plugin:
            ingress_guard.plugin.ready = False
        if core:
            await core.stop()
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if job:
            job.Close()
        if runner:
            await runner.cleanup()
        if record_path.exists():
            try:
                if (
                    json.loads(record_path.read_text(encoding="utf-8")).get("pid")
                    == os.getpid()
                ):
                    record_path.unlink()
            except Exception:
                pass
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-root", type=Path)
    parser.add_argument("--port", type=int, default=6185)
    args = parser.parse_args()
    root = args.smoke_root.resolve() if args.smoke_root else ROOT
    if args.smoke_root and not root.is_relative_to(ROOT / "runtime" / "test-state"):
        raise ValueError("smoke_root_refused")
    os.environ.update(
        QQAGENT_ROOT=str(root),
        ASTRBOT_ROOT=str(root / "data" / "astrbot"),
        NAPCAT_WORKDIR=str(root / "data" / "napcat"),
        TEMP=str(root / "runtime" / "tmp"),
        TMP=str(root / "runtime" / "tmp"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    (root / "runtime" / "tmp").mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(run(root, bool(args.smoke_root), args.port))
    except Exception as exc:
        # Never print exception text: upstream errors may contain content or credentials.
        state = root / "runtime" / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "last_error.json").write_text(
            json.dumps(
                {"code": "startup_or_runtime_failed", "type": type(exc).__name__}
            ),
            encoding="utf-8",
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
