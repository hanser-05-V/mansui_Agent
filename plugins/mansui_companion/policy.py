from .domain import Message, Route


def admit(raw, owner: str, groups: frozenset[str], expected_bot: str) -> bool:
    if (
        not owner.isascii()
        or not owner.isdigit()
        or not expected_bot.isascii()
        or not expected_bot.isdigit()
    ):
        return False
    if raw.get("post_type") != "message":
        return False
    bot, sender = str(raw.get("self_id", "")), str(raw.get("user_id", ""))
    if (
        bot != expected_bot
        or not sender.isascii()
        or not sender.isdigit()
        or sender == bot
    ):
        return False
    if raw.get("message_type") == "private":
        return sender == owner
    if raw.get("message_type") == "group":
        return str(raw.get("group_id", "")) in groups
    return False


def decide(message: Message, owner: str, groups: frozenset[str]) -> Route:
    if message.sender == message.bot:
        return Route.DROP
    if message.group is None:
        return Route.REQUIRED if message.sender == owner else Route.DROP
    if message.group not in groups:
        return Route.DROP
    if message.sender == owner or message.bot in message.mentions:
        return Route.REQUIRED
    if not message.text.strip():
        return Route.DROP
    return Route.OPTIONAL
