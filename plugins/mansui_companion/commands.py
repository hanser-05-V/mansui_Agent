from .affinity import stage
from .memory import Memory

HELP = "可用命令：/满穗 关系、记忆、记住 文本、纠正 编号 新文本、遗忘 编号、重置关系 确认、状态。仅管理当前私聊。"


def handle(message, store, settings):
    if (
        message.group
        or message.sender != settings.owner_qq
        or not message.text.startswith("/满穗")
    ):
        return None
    parts = message.text.split(maxsplit=2)
    command = parts[1] if len(parts) > 1 else "帮助"
    rest = parts[2] if len(parts) > 2 else ""
    mem = Memory(store)
    try:
        if command == "帮助":
            return HELP
        if command == "关系":
            state = store.relation(message.scope, message.sender)
            return f"我们目前是「{stage(state.score)}」，好感度 {state.score}/100。"
        if command == "重置关系":
            if rest != "确认":
                return "如要重置当前私聊关系，请发送 /满穗 重置关系 确认"
            with store.db:
                store.db.execute(
                    "DELETE FROM relations WHERE scope=? AND subject=?",
                    (message.scope, message.sender),
                )
            return "当前私聊关系已重置为 20，记忆保留。"
        if command == "记住":
            if not rest.strip():
                return "在「记住」后写下希望我记住的事。"
            seq = store.event(message.key)["seq"]
            item = mem.add(message.scope, message.sender, rest, [seq])
            return f"记住了，编号 {item}。"
        if command == "记忆":
            rows = mem.list(message.scope, message.sender)
            return (
                "\n".join(f"{r['id']}：{r['text']}" for r in rows)[:3900]
                or "当前私聊还没有保存长期记忆。"
            )
        if command == "遗忘":
            mem.forget(message.scope, message.sender, int(rest))
            return "已遗忘，并清除了该来源消息的上下文及关联摘要。"
        if command == "纠正":
            ident, text = rest.split(maxsplit=1)
            mem.correct(message.scope, message.sender, int(ident), text)
            return "已纠正，并清除了旧来源的上下文及关联摘要。"
        if command == "状态":
            return f"当前服务已接收消息。待处理故障记录：{len(store.pending())}。详细状态请在本机查看。"
        return HELP
    except (ValueError, TypeError):
        return "没有找到当前私聊的该记忆，或命令格式有误。发送 /满穗 帮助 查看用法。"
