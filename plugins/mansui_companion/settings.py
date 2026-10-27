import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path


def account(value):
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isdigit()
        and 4 <= len(value) <= 20
    )


@dataclass(frozen=True)
class Settings:
    owner_qq: str
    bot_qq: str
    allowed_groups: tuple[str, ...] = ()
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    max_concurrency: int = 2
    queue_size: int = 10
    chat_max_tokens: int = 512
    long_answer_max_tokens: int = 1024
    history_limit: int = 24
    raw_retention_days: int = 30
    optional_stale_seconds: int = 120
    cost_reminder_cny: str | None = None
    pricing: dict | None = None
    ready: bool = False
    deepseek_api_key: str = field(default="", repr=False)
    onebot_token: str = field(default="", repr=False)
    control_token: str = field(default="", repr=False)

    @classmethod
    def from_dict(cls, value: dict, secrets: dict | None = None, *, require_ready=True):
        if not isinstance(value, dict) or not isinstance(secrets or {}, dict):
            raise ValueError("invalid_configuration")
        secret = secrets or {}
        permitted = set(cls.__dataclass_fields__) - {
            "deepseek_api_key",
            "onebot_token",
            "control_token",
        }
        if set(value) - permitted:
            raise ValueError("unknown_configuration_fields")
        cfg = cls(
            **value,
            **{
                k: secret.get(k, "")
                for k in ("deepseek_api_key", "onebot_token", "control_token")
            },
        )
        if require_ready and not cfg.ready:
            raise ValueError("configuration_not_ready")
        if require_ready or cfg.owner_qq or cfg.bot_qq:
            if (
                not account(cfg.owner_qq)
                or not account(cfg.bot_qq)
                or cfg.owner_qq == cfg.bot_qq
            ):
                raise ValueError("invalid_owner_or_bot")
        if not isinstance(cfg.allowed_groups, (list, tuple)) or any(
            not account(g) for g in cfg.allowed_groups
        ):
            raise ValueError("invalid_groups")
        if (
            cfg.base_url != "https://api.deepseek.com"
            or not isinstance(cfg.model, str)
            or not cfg.model.strip()
        ):
            raise ValueError("invalid_model_endpoint")
        for name, upper in (
            ("max_concurrency", 2),
            ("queue_size", 10),
            ("chat_max_tokens", 512),
            ("long_answer_max_tokens", 1024),
            ("history_limit", 24),
            ("raw_retention_days", 30),
            ("optional_stale_seconds", 3600),
        ):
            n = getattr(cfg, name)
            if type(n) is not int or not 1 <= n <= upper:
                raise ValueError("invalid_" + name)
        if type(cfg.ready) is not bool or any(
            not isinstance(getattr(cfg, k), str)
            for k in ("deepseek_api_key", "onebot_token", "control_token")
        ):
            raise ValueError("invalid_configuration_types")
        try:
            if cfg.cost_reminder_cny is not None:
                limit = Decimal(str(cfg.cost_reminder_cny))
                if not limit.is_finite() or limit <= 0:
                    raise ValueError("invalid_cost_reminder")
            if cfg.pricing is not None:
                p = cfg.pricing
                if (
                    not isinstance(p, dict)
                    or p.get("currency") != "CNY"
                    or p.get("model") != cfg.model
                    or not p.get("effective_at")
                ):
                    raise ValueError("invalid_pricing")
                for key in (
                    "cache_hit_input_per_million",
                    "cache_miss_input_per_million",
                    "output_per_million",
                ):
                    rate = Decimal(str(p[key]))
                    if not rate.is_finite() or rate < 0:
                        raise ValueError("invalid_pricing")
        except (InvalidOperation, KeyError, TypeError) as exc:
            raise ValueError("invalid_pricing") from exc
        object.__setattr__(
            cfg, "allowed_groups", tuple(dict.fromkeys(cfg.allowed_groups))
        )
        return cfg


def load_settings(
    path: Path, secrets_path: Path | None = None, *, require_ready=True
) -> Settings:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    secrets = (
        json.loads(Path(secrets_path).read_text(encoding="utf-8-sig"))
        if secrets_path and Path(secrets_path).exists()
        else {}
    )
    return Settings.from_dict(value, secrets, require_ready=require_ready)
