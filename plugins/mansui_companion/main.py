from pathlib import Path
import os
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from .settings import load_settings
from .store import Store
from .usage import Usage
from .deepseek import DeepSeek
from .service import Service
from .onebot import send_text
from scripts import ingress_guard


class MansuiPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.ready = False
        self.service = None
        self.store = None
        self.bot = None

    async def initialize(self):
        if not ingress_guard.installed:
            raise RuntimeError("ingress_guard_required")
        root = Path(os.environ["QQAGENT_ROOT"])
        cfg = load_settings(
            root / "config" / "mansui.local.json",
            root / "config" / "secrets.local.json",
        )
        self.store = Store(root / "data" / "mansui.sqlite3")
        self.usage = Usage(self.store, cfg.model, cfg.pricing, cfg.cost_reminder_cny)
        model = DeepSeek(cfg, self.usage)

        async def send(message, text):
            if self.bot is None:
                raise RuntimeError("onebot_disconnected")
            return await send_text(self.bot, message, text)

        self.service = Service(cfg, self.store, model, send)
        self.store.prune_raw(days=cfg.raw_retention_days)
        ingress_guard.plugin = self
        self.ready = True

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def on_message(self, event: AstrMessageEvent):
        if event.get_platform_id() != "mansui_onebot":
            return
        event.stop_event()
        if not self.ready or not ingress_guard.is_ready():
            return
        self.bot = event.bot
        self.service.receive(event.message_obj.raw_message)

    async def terminate(self):
        self.ready = False
        if ingress_guard.plugin is self:
            ingress_guard.plugin = None
        if self.service:
            await self.service.close()
        if self.store:
            self.store.close()
            self.store = None
