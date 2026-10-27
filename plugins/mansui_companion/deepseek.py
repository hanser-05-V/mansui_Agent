import asyncio
import json
import random
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from .domain import Reply

FALLBACK = "这次没整理好回复，再和我说一遍好吗？"


class ModelError(Exception):
    pass


def parse_reply(content, required):
    try:
        value = json.loads(content)
        if not isinstance(value, dict) or set(value) - {
            "participate",
            "text",
            "affinity_delta",
            "affinity_reason",
        }:
            raise ValueError()
        participate = value.get("participate")
        text = value.get("text")
        if type(participate) is not bool or not isinstance(text, str):
            raise ValueError()
        text = text.strip()
        if (
            len(text) > 4000
            or (participate and not text)
            or (required and not participate)
        ):
            raise ValueError()
        if not participate and text:
            raise ValueError()
        delta = value.get("affinity_delta", 0)
        if type(delta) is not int or delta not in (-1, 0, 1):
            delta = 0
        reason = value.get("affinity_reason", "")
        return Reply(
            participate,
            text,
            delta,
            reason[:100] if isinstance(reason, str) else "",
            True,
        )
    except (ValueError, TypeError):
        return Reply(required, FALLBACK if required else "", 0, "", False)


def retry_after(value, now=None):
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else None
    except (ValueError, TypeError):
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max(0, (when - (now or datetime.now(timezone.utc))).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


class DeepSeek:
    def __init__(self, settings, usage, client=None, sleep=asyncio.sleep):
        self.settings = settings
        self.usage = usage
        self.sleep = sleep
        self.semaphore = asyncio.Semaphore(settings.max_concurrency)
        if client is None:
            import httpx

            client = httpx.AsyncClient(
                timeout=45, follow_redirects=False, trust_env=False
            )
        self.client = client

    async def close(self):
        await self.client.aclose()

    async def complete(self, messages, purpose="chat", max_tokens=512, event_seq=None):
        if type(max_tokens) is not int or not 1 <= max_tokens <= 1024:
            raise ValueError("invalid_output_limit")
        body = {
            "model": self.settings.model,
            "messages": messages,
            "stream": False,
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        for attempt in range(3):
            meter = self.usage.begin(event_seq, purpose)
            delay = 2**attempt + random.random() * 0.2
            code = None
            try:
                async with self.semaphore:
                    response = await self.client.post(
                        self.settings.base_url + "/chat/completions",
                        json=body,
                        headers={
                            "Authorization": "Bearer " + self.settings.deepseek_api_key
                        },
                    )
                status = response.status_code
                if status == 200:
                    usage = None
                    try:
                        data = response.json()
                        if not isinstance(data, dict):
                            raise ValueError()
                        usage = data.get("usage")

                        choice = data["choices"][0]
                        message = choice["message"]
                        if choice.get("finish_reason") != "stop" or message.get(
                            "tool_calls"
                        ):
                            raise ValueError()
                        content = message["content"]
                        if not isinstance(content, str) or not content.strip():
                            raise ValueError()
                        self.usage.finish(meter, "ok", usage)
                        return content
                    except (
                        ValueError,
                        KeyError,
                        IndexError,
                        TypeError,
                        AttributeError,
                    ):
                        self.usage.finish(
                            meter, "invalid", usage, "model_output_invalid"
                        )
                        raise ModelError("model_output_invalid") from None
                code = "http_" + str(status)
                self.usage.finish(meter, "failed", None, code)
                if status not in (429, 500, 502, 503, 504):
                    raise ModelError(code)
                wait = retry_after(response.headers.get("Retry-After"))
                if wait is not None:
                    if wait > 30:
                        raise ModelError("rate_limit_wait_too_long")
                    delay = max(delay, wait)
            except asyncio.CancelledError:
                self.usage.finish(meter, "cancelled", None, "cancelled")
                raise
            except ModelError:
                raise
            except Exception as exc:
                code = "network_error"
                self.usage.finish(meter, "failed", None, code)
                if type(exc).__name__ not in (
                    "ConnectError",
                    "ConnectTimeout",
                    "ReadTimeout",
                    "ReadError",
                    "WriteError",
                    "WriteTimeout",
                    "PoolTimeout",
                    "RemoteProtocolError",
                    "TimeoutError",
                    "ConnectionError",
                ):
                    raise ModelError("transport_error") from None
            if attempt == 2:
                raise ModelError(code or "request_failed")
            await self.sleep(delay)
        raise ModelError("request_failed")
