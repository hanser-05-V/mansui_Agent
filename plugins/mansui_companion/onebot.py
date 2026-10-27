import asyncio
import re
import time
from .domain import Message

SECRET_PATTERN = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{16,})", re.I
)
SECRET_NOTICE = "[凭据已拦截，请通过本机配置满穗入口填写]"


class DeliveryUnknown(Exception):
    pass


class SendRejected(Exception):
    pass


def contains_secret(text, settings):
    return bool(SECRET_PATTERN.search(text)) or any(
        value and value in text
        for value in (
            settings.deepseek_api_key,
            settings.onebot_token,
            settings.control_token,
        )
    )


def normalize(raw, settings):
    segments = raw.get("message", [])
    text = []
    mentions = set()
    unsupported = False
    if not isinstance(segments, list):
        segments = []
        unsupported = True
    for segment in segments[:100]:
        if not isinstance(segment, dict) or not isinstance(segment.get("data"), dict):
            unsupported = True
            continue
        data = segment["data"]
        if segment.get("type") == "text" and isinstance(data.get("text"), str):
            text.append(data["text"][:4001])
        elif segment.get("type") == "at":
            qq = str(data.get("qq", ""))
            if qq == settings.bot_qq:
                mentions.add(qq)
        else:
            unsupported = True
    body = "".join(text)
    if contains_secret(body, settings):
        body = SECRET_NOTICE
    group = str(raw["group_id"]) if raw.get("message_type") == "group" else None
    mid = raw.get("message_id")
    if mid is None or not str(mid) or len(str(mid)) > 100:
        raise ValueError("missing_platform_message_id")
    # Queue age is local receipt time; remote timestamps are not trusted.
    return Message(
        str(raw["self_id"]),
        str(raw["user_id"]),
        group,
        str(mid),
        body[:4001],
        frozenset(mentions),
        time.time(),
        unsupported,
    )


def sanitized_raw(raw, message):
    result = {
        key: raw[key]
        for key in ("post_type", "message_type", "self_id", "user_id", "message_id")
        if key in raw
    }
    result.update(
        time=int(message.received_at),
        sub_type="normal" if message.group else "friend",
        sender={"user_id": int(message.sender), "nickname": message.sender},
    )
    if message.group:
        result["group_id"] = int(message.group)
    result["message"] = [{"type": "text", "data": {"text": message.text}}]
    if message.bot in message.mentions:
        result["message"].append({"type": "at", "data": {"qq": message.bot}})
    result["raw_message"] = message.text
    result["_qqagent_message"] = message
    return result


async def send_text(bot, message, text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty_send")
    segments = [{"type": "text", "data": {"text": text[:4000]}}]
    action = "send_group_msg" if message.group else "send_private_msg"
    target = (
        {"group_id": int(message.group)}
        if message.group
        else {"user_id": int(message.sender)}
    )
    try:
        result = await asyncio.wait_for(
            bot.call_action(action, **target, message=segments, auto_escape=True), 20
        )
    except Exception as exc:
        if type(exc).__name__ == "ActionFailed":
            raise SendRejected("platform_rejected") from None
        raise DeliveryUnknown("delivery_unknown") from None
    if not isinstance(result, dict) or result.get("message_id") is None:
        raise DeliveryUnknown("missing_receipt")
    return str(result["message_id"])
