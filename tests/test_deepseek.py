import unittest
import json
from test_storage import capability
from plugins.mansui_companion.settings import Settings


class Response:
    def __init__(self, status=200, value=None, headers=None):
        self.status_code = status
        self.value = value
        self.headers = headers or {}

    def json(self):
        return self.value


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.closed = False

    async def post(self, url, **kw):
        self.calls.append((url, kw))
        return next(self.responses)

    async def aclose(self):
        self.closed = True


class Meter:
    def __init__(self):
        self.started = []
        self.finished = []

    def begin(self, event, purpose):
        self.started.append((event, purpose))
        return len(self.started)

    def finish(self, *args):
        self.finished.append(args)


def ok(content=None):
    return Response(
        value={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": content
                        or json.dumps(
                            {"participate": True, "text": "你好", "affinity_delta": 0}
                        ),
                        "reasoning_content": "NEVER_SAVE",
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 3,
                "prompt_cache_hit_tokens": 2,
                "prompt_cache_miss_tokens": 8,
            },
        }
    )


class DeepSeekTests(unittest.IsolatedAsyncioTestCase):
    async def run_client(self, responses):
        self.client = Client(responses)
        self.meter = Meter()
        self.delays = []

        async def sleep(delay):
            self.delays.append(delay)

        cfg = Settings("10001", "90001", deepseek_api_key="TEST_SECRET")
        return capability("deepseek").DeepSeek(
            cfg, self.meter, client=self.client, sleep=sleep
        )

    async def test_payload_non_thinking_and_no_reasoning_persistence(self):
        model = await self.run_client([ok()])
        result = await model.complete(
            [
                {"role": "system", "content": "return JSON"},
                {"role": "user", "content": "hi"},
            ]
        )
        self.assertEqual(
            result,
            '{"participate": true, "text": "\\u4f60\\u597d", "affinity_delta": 0}',
        )
        body = self.client.calls[0][1]["json"]
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertFalse(body["stream"])
        self.assertNotIn("tools", body)
        self.assertNotIn("NEVER_SAVE", str(self.meter.finished))
        await model.close()
        self.assertTrue(self.client.closed)

    async def test_retry_after_and_auth_no_retry(self):
        model = await self.run_client(
            [Response(429, headers={"Retry-After": "2"}), ok()]
        )
        await model.complete([{"role": "user", "content": "json"}])
        self.assertEqual(len(self.client.calls), 2)
        self.assertGreaterEqual(self.delays[0], 2)
        model = await self.run_client([Response(401), ok()])
        with self.assertRaises(capability("deepseek").ModelError):
            await model.complete([])
        self.assertEqual(len(self.client.calls), 1)

    async def test_three_attempts_and_excessive_retry_after(self):
        model = await self.run_client([Response(503)] * 4)
        with self.assertRaises(capability("deepseek").ModelError):
            await model.complete([])
        self.assertEqual(len(self.client.calls), 3)
        model = await self.run_client([Response(429, headers={"Retry-After": "3600"})])
        with self.assertRaises(capability("deepseek").ModelError):
            await model.complete([])
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.delays, [])

    def test_strict_reply_required_fallback_optional_silent(self):
        parse = capability("deepseek").parse_reply
        for content in ("{}", "[]", "invalid", '{"participate":false,"text":""}'):
            r = parse(content, True)
            self.assertTrue(r.participate)
            self.assertFalse(r.valid)
            self.assertTrue(r.text)
        self.assertFalse(parse("invalid", False).participate)
        self.assertEqual(
            parse(
                '{"participate":true,"text":"ok","affinity_delta":true}', True
            ).affinity_delta,
            0,
        )
        self.assertFalse(
            parse('{"participate":true,"text":"ok","target":"999"}', True).valid
        )

    async def test_invalid_envelope_records_attempt_and_httpx_transport(self):
        import httpx

        async def transport(request):
            return httpx.Response(200, json=[])

        meter = Meter()
        model = capability("deepseek").DeepSeek(
            Settings("10001", "90001"),
            meter,
            client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
        )
        with self.assertRaises(capability("deepseek").ModelError):
            await model.complete([])
        self.assertEqual(len(meter.started), 1)
        self.assertEqual(len(meter.finished), 1)
        await model.close()

    def test_retry_after_http_date_and_non_finite_value(self):
        from datetime import datetime, timezone

        retry = capability("deepseek").retry_after
        now = datetime(2026, 10, 27, 0, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(retry("Tue, 27 Oct 2026 00:00:03 GMT", now), 3)
        self.assertIsNone(retry("NaN", now))
