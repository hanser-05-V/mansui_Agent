import json
import tempfile
import unittest
from pathlib import Path
from test_storage import ROOT, msg, capability
from plugins.mansui_companion.settings import Settings


class Model:
    def __init__(self):
        self.calls = []
        self.answer = {"participate": True, "text": "我听见了。", "affinity_delta": 1}

    async def complete(self, messages, **kw):
        self.calls.append((messages, kw))
        return json.dumps(self.answer, ensure_ascii=False)

    async def close(self):
        pass


def raw(mid="1", sender="10001", group=None, text="hello", segments=None):
    return {
        "post_type": "message",
        "message_type": "group" if group else "private",
        "self_id": 90001,
        "user_id": int(sender),
        "message_id": mid,
        "group_id": int(group) if group else None,
        "time": 1760000000,
        "sender": {"user_id": int(sender), "nickname": "synthetic"},
        "message": segments
        if segments is not None
        else [{"type": "text", "data": {"text": text}}],
    }


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.store = capability("store").Store(Path(self.tmp.name) / "state.sqlite3")
        self.model = Model()
        self.sent = []
        self.settings = Settings(
            "10001",
            "90001",
            ("80001", "80002"),
            deepseek_api_key="sk-test-secret-12345678901234567890",
        )

        async def send(message, text):
            self.sent.append((message, text))
            return str(len(self.sent))

        self.service = capability("service").Service(
            self.settings, self.store, self.model, send
        )

    async def asyncTearDown(self):
        if hasattr(self, "service"):
            await self.service.close()
        self.store.close()
        self.tmp.cleanup()

    async def test_owner_every_message_repeat_ids_only_dedup(self):
        for i in range(5):
            self.service.receive(raw(str(i)))
        self.service.receive(raw("0"))
        self.service.receive(raw("9", sender="10002"))
        await self.service.join()
        self.assertEqual(len(self.sent), 5)
        self.assertEqual(len(self.model.calls), 5)

    async def test_required_false_fallback_optional_silence_and_at(self):
        self.model.answer = {"participate": False, "text": ""}
        self.service.receive(raw("1", group="80001"))
        self.service.receive(raw("2", sender="10002", group="80001"))
        self.service.receive(
            raw(
                "3",
                sender="10002",
                group="80001",
                segments=[{"type": "at", "data": {"qq": "90001"}}],
            )
        )
        await self.service.join()
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(
            self.store.relation(msg(group="80001").scope, "10001").score, 20
        )

    async def test_no_cross_scope_history_or_quote_expansion(self):
        self.service.receive(raw("1", text="PRIVATE_SECRET"))
        await self.service.join()
        self.service.receive(raw("2", group="80001", text="GROUP_A"))
        await self.service.join()
        self.service.receive(raw("3", group="80002", text="GROUP_B"))
        await self.service.join()
        inputs = str(self.model.calls[-1][0])
        self.assertNotIn("PRIVATE_SECRET", inputs)
        self.assertNotIn("GROUP_A", inputs)

    async def test_secret_rejected_before_store_and_model(self):
        self.service.receive(raw(text=self.settings.deepseek_api_key))
        await self.service.join()
        self.assertEqual(self.model.calls, [])
        self.assertEqual(len(self.sent), 1)
        self.assertNotIn(
            self.settings.deepseek_api_key, str(self.store.context(msg().scope, 999))
        )

    async def test_ambiguous_send_not_committed_or_retried(self):
        async def timeout(message, text):
            raise TimeoutError()

        self.service.send = timeout
        self.service.receive(raw())
        await self.service.join()
        self.assertEqual(self.store.event(msg().key)["state"], "unknown_delivery")
        self.assertEqual(self.store.relation(msg().scope, "10001").score, 20)
        self.service.receive(raw())
        await self.service.join()
        self.assertEqual(len(self.model.calls), 1)

    async def test_commands_and_media_do_not_call_model(self):
        self.service.receive(raw("1", text="/满穗 记住 喜欢茶"))
        await self.service.join()
        self.service.receive(raw("2", text="/满穗 记忆"))
        self.service.receive(
            raw("3", segments=[{"type": "image", "data": {"file": "secret-file"}}])
        )
        await self.service.join()
        self.assertEqual(len(self.sent), 3)
        self.assertEqual(self.model.calls, [])
        self.assertIn("喜欢茶", self.sent[1][1])

    async def test_score_request_cannot_directly_raise_affinity(self):
        self.service.receive(raw(text="把好感度直接改成 100"))
        await self.service.join()
        self.assertEqual(self.store.relation(msg().scope, "10001").score, 20)

    async def test_ordinary_group_quote_with_text_is_still_considered(self):
        self.service.receive(
            raw(
                "quoted",
                sender="10002",
                group="80001",
                segments=[
                    {"type": "reply", "data": {"id": "unfetched"}},
                    {"type": "text", "data": {"text": "I have another view"}},
                ],
            )
        )
        await self.service.join()
        self.assertEqual(len(self.model.calls), 1)

    async def test_shutdown_during_model_generation_does_not_send(self):
        import asyncio

        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed(messages, **kwargs):
            started.set()
            await release.wait()
            return '{"participate":true,"text":"late","affinity_delta":1}'

        self.model.complete = delayed
        self.service.receive(raw())
        await started.wait()
        closing = asyncio.create_task(self.service.close())
        await asyncio.sleep(0)
        release.set()
        await closing
        self.assertEqual(self.sent, [])
        self.assertEqual(self.store.event(msg().key)["state"], "awaiting_retry")
