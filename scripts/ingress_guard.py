import inspect
from plugins.mansui_companion.policy import admit
from plugins.mansui_companion.onebot import normalize, sanitized_raw

plugin = None
installed = False


def is_ready():
    return installed and plugin is not None and getattr(plugin, "ready", False)


def install_guard(adapter_type, settings, ready=is_ready):
    global installed
    original = adapter_type.convert_message
    if getattr(original, "_qqagent_guard", False):
        raise RuntimeError("guard_already_installed")
    if list(inspect.signature(original).parameters) != ["self", "event"]:
        raise RuntimeError("unsupported_adapter_signature")

    async def guarded(self, event):
        if not ready() or not admit(
            event,
            settings.owner_qq,
            frozenset(settings.allowed_groups),
            settings.bot_qq,
        ):
            return None
        try:
            message = normalize(event, settings)
            clean = sanitized_raw(event, message)
            if type(event) is not dict:
                clean = type(event)(clean)
            return await original(self, clean)
        except Exception:
            if plugin is not None and getattr(plugin, "store", None):
                plugin.store.status("ingress", "conversion_failed")
            return None

    guarded._qqagent_guard = True
    adapter_type.convert_message = guarded
    if adapter_type.__module__.startswith("astrbot."):
        constructor = getattr(
            adapter_type, "_qqagent_original_init", adapter_type.__init__
        )

        def protected_init(self, *args, **kwargs):
            constructor(self, *args, **kwargs)
            from quart import abort, websocket

            async def refuse_http():
                abort(404)

            async def check_bot_identity():
                if websocket.headers.get("X-Self-ID") != settings.bot_qq:
                    abort(403)

            self.bot.server_app.before_request(refuse_http)
            self.bot.server_app.before_websocket(check_bot_identity)

        adapter_type._qqagent_original_init = constructor
        adapter_type.__init__ = protected_init
    installed = True
    return original
