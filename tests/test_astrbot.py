import asyncio
import importlib
import unittest
from test_service import raw
from plugins.mansui_companion.settings import Settings


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_before_conversion_and_fail_closed(self):
        try:
            guard = importlib.import_module("scripts.ingress_guard")
        except ModuleNotFoundError as exc:
            self.fail(str(exc))
        cfg = Settings("10001", "90001", ("80001",))
        calls = []

        class Adapter:
            async def convert_message(self, event):
                calls.append(event)
                return event

        ready = True
        original = guard.install_guard(Adapter, cfg, lambda: ready)
        try:
            obj = Adapter()
            self.assertIsNone(
                await obj.convert_message(raw(sender="10002", text="PRIVATE_CANARY"))
            )
            self.assertEqual(calls, [])
            data = await obj.convert_message(
                raw(
                    text="hello",
                    segments=[
                        {"type": "reply", "data": {"id": "other-private"}},
                        {"type": "text", "data": {"text": "hello"}},
                    ],
                )
            )
            self.assertEqual([s["type"] for s in data["message"]], ["text"])
            self.assertNotIn("other-private", str(data))
            ready = False
            self.assertIsNone(await obj.convert_message(raw()))
            self.assertEqual(len(calls), 1)
        finally:
            Adapter.convert_message = original

    async def test_pure_text_send_and_target(self):
        from plugins.mansui_companion.onebot import send_text, normalize

        cfg = Settings("10001", "90001")

        class Bot:
            async def call_action(self, action, **kwargs):
                self.action = action
                self.kw = kwargs
                return {"message_id": 22}

        bot = Bot()
        message = normalize(raw(), cfg)
        result = await send_text(bot, message, "[CQ:at,qq=all]")
        self.assertEqual(result, "22")
        self.assertEqual(bot.action, "send_private_msg")
        self.assertEqual(
            bot.kw["message"], [{"type": "text", "data": {"text": "[CQ:at,qq=all]"}}]
        )
        self.assertEqual(bot.kw["user_id"], 10001)

    def test_generated_framework_config_disables_competing_reply(self):
        try:
            module = importlib.import_module("scripts.configure")
        except ModuleNotFoundError as exc:
            self.fail(str(exc))
        cfg = Settings(
            "10001", "90001", onebot_token="fake-token", control_token="fake-control"
        )
        data = module.framework_config(cfg)
        self.assertFalse(data["provider_settings"]["enable"])
        self.assertFalse(data["trace_enable"])
        self.assertFalse(data["log_file_enable"])
        self.assertTrue(data["disable_builtin_commands"])
        self.assertTrue(data["disable_metrics"])
        self.assertEqual(data["platform"][0]["ws_reverse_host"], "127.0.0.1")
        self.assertFalse(data["platform_settings"]["enable_id_white_list"])


async def test_real_adapter_pipeline_and_ws_auth():
    import os
    import shutil
    from pathlib import Path
    import pytest
    from scripts import ingress_guard
    from plugins.mansui_companion.settings import load_settings

    root = Path(os.environ["QQAGENT_ROOT"])
    source = Path(r"E:\QQAgent\plugins\mansui_companion")
    target = root / "data" / "astrbot" / "data" / "plugins" / "mansui_companion"
    shutil.copytree(source, target, dirs_exist_ok=True)
    import sys

    sys.path.insert(0, str(root / "data" / "astrbot"))
    from astrbot.core import db_helper, LogBroker
    from astrbot.core import core_lifecycle
    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
        AiocqhttpAdapter,
    )
    from aiocqhttp import Event
    from loguru import logger

    logger.disable("")

    async def no_fetch():
        pass

    core_lifecycle.update_llm_metadata = no_fetch
    cfg = load_settings(
        root / "config" / "mansui.local.json", root / "config" / "secrets.local.json"
    )
    original = ingress_guard.install_guard(AiocqhttpAdapter, cfg)
    core = core_lifecycle.AstrBotCoreLifecycle(LogBroker(), db_helper)
    try:
        await core.initialize()
        assert ingress_guard.is_ready(), str(core.plugin_manager.failed_plugin_dict)
        plugin = ingress_guard.plugin
        await plugin.service.model.close()
        from test_service import Model

        model = Model()
        plugin.service.model = model
        adapter = next(
            p
            for p in core.platform_manager.platform_insts
            if p.meta().id == "mansui_onebot"
        )
        sent = []

        async def send(action, **kw):
            sent.append((action, kw))
            return {"message_id": len(sent)}

        real_action = adapter.bot.call_action
        adapter.bot.call_action = send
        assert (
            await adapter.convert_message(
                Event(raw("framework-no", sender="10002", text="PRIVATE_DENIED_CANARY"))
            )
            is None
        )
        clean = await adapter.convert_message(
            Event(
                raw(
                    "framework-yes-" + __import__("uuid").uuid4().hex,
                    group="80001",
                    text="owner without mention",
                )
            )
        )
        assert clean is not None
        event = adapter.create_event(clean)
        scheduler = next(iter(core.pipeline_scheduler_mapping.values()))
        await scheduler.execute(event)
        await plugin.service.join()
        assert len(sent) == 1
        assert sent[0][0] == "send_group_msg" and sent[0][1]["group_id"] == 80001
        assert len(model.calls) == 1
        assert event.is_stopped()
        assert "PRIVATE_DENIED_CANARY" not in str(model.calls)
        plugin.ready = False
        assert await adapter.convert_message(Event(raw("framework-off"))) is None
        client = adapter.bot.server_app.test_client()
        from quart.testing.connections import WebsocketResponseError

        with pytest.raises(WebsocketResponseError):
            async with client.websocket(
                "/ws",
                headers={
                    "X-Self-ID": "90001",
                    "X-Client-Role": "Universal",
                    "Authorization": "Bearer WRONG",
                },
            ):
                pass
        # Exercise the pinned aiocqhttp API result envelope over an in-memory WS.
        plugin.ready = True
        adapter.bot.call_action = real_action
        async with client.websocket(
            "/ws",
            headers={
                "X-Self-ID": "90001",
                "X-Client-Role": "Universal",
                "Authorization": "Bearer " + cfg.onebot_token,
            },
        ) as ws:
            await ws.send_json(
                raw("wire-" + __import__("uuid").uuid4().hex, text="wire message")
            )
            wire_event = await asyncio.wait_for(core.event_queue.get(), 3)
            await scheduler.execute(wire_event)
            action = await asyncio.wait_for(ws.receive_json(), 3)
            assert action["action"] == "send_private_msg"
            assert action["params"]["user_id"] == 10001
            assert action["params"]["message"][0]["type"] == "text"
            await ws.send_json(
                {
                    "status": "ok",
                    "retcode": 0,
                    "data": {"message_id": 7722},
                    "echo": action["echo"],
                }
            )
            await plugin.service.join()
            assert (
                plugin.store.db.execute(
                    "SELECT count(*) FROM events WHERE sent_id='7722'"
                ).fetchone()[0]
                >= 1
            )
        response = await client.post(
            "/", json=raw("HTTP_FORGED"), headers={"X-Self-ID": "90001"}
        )
        assert response.status_code in (401, 403, 404)
    finally:
        if hasattr(core, "curr_tasks"):
            await core.stop()
        AiocqhttpAdapter.convert_message = original
        ingress_guard.plugin = None
        ingress_guard.installed = False
