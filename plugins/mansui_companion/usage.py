import json
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal


def estimate_cny(hit, miss, output, prices):
    if prices is None or any(type(v) is not int or v < 0 for v in (hit, miss, output)):
        return None
    try:
        rates = [
            Decimal(str(prices[k]))
            for k in (
                "cache_hit_input_per_million",
                "cache_miss_input_per_million",
                "output_per_million",
            )
        ]
        if any(not r.is_finite() or r < 0 for r in rates):
            return None
        return sum(
            (Decimal(n) * r for n, r in zip((hit, miss, output), rates)), Decimal(0)
        ) / Decimal(1000000)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None


class Usage:
    def __init__(self, store, model, pricing=None, reminder=None):
        self.store = store
        self.model = model
        self.pricing = pricing
        self.reminder = reminder

    def begin(self, event_seq, purpose):
        with self.store.db:
            return self.store.db.execute(
                "INSERT INTO usage_attempts(event_seq,purpose,model,started_at,status) VALUES(?,?,?,?,'inflight')",
                (event_seq, purpose, self.model, time.time()),
            ).lastrowid

    def finish(self, attempt, status, usage, error_code=None):
        values = []
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
        ):
            n = usage.get(key) if isinstance(usage, dict) else None
            values.append(n if type(n) is int and n >= 0 else None)
        inp, out, hit, miss = values
        price = self.pricing
        valid_price = (
            isinstance(price, dict)
            and price.get("model") == self.model
            and price.get("currency") == "CNY"
            and price.get("effective_at")
        )
        cost = (
            estimate_cny(hit, miss, out, price)
            if valid_price
            and inp is not None
            and hit is not None
            and miss is not None
            and hit + miss == inp
            else None
        )
        with self.store.db:
            self.store.db.execute(
                "UPDATE usage_attempts SET status=?,error_code=?,input_tokens=?,output_tokens=?,cache_hit=?,cache_miss=?,estimated_cny=?,pricing_snapshot=? WHERE id=?",
                (
                    status,
                    error_code,
                    *values,
                    str(cost) if cost is not None else None,
                    json.dumps(price) if valid_price else None,
                    attempt,
                ),
            )
        if self.reminder is not None:
            reached = Decimal(self.summary()["known_estimate_cny"]) >= Decimal(
                self.reminder
            )
            self.store.status(
                "cost", "reminder_reached" if reached else "below_reminder"
            )

    def summary(self, period="day", now=None):
        now = now or datetime.now(timezone(timedelta(hours=8)))
        local = now.astimezone(timezone(timedelta(hours=8)))
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "month":
            start = start.replace(day=1)
        rows = self.store.db.execute(
            "SELECT * FROM usage_attempts WHERE started_at>=? AND started_at<?",
            (start.timestamp(), now.timestamp() + 1),
        ).fetchall()
        return {
            "attempts": len(rows),
            "unknown_usage": sum(
                r["input_tokens"] is None or r["output_tokens"] is None for r in rows
            ),
            "unknown_cost": sum(r["estimated_cny"] is None for r in rows),
            "known_input_tokens": sum(r["input_tokens"] or 0 for r in rows),
            "known_output_tokens": sum(r["output_tokens"] or 0 for r in rows),
            "known_estimate_cny": str(
                sum(
                    (
                        Decimal(r["estimated_cny"])
                        for r in rows
                        if r["estimated_cny"] is not None
                    ),
                    Decimal(0),
                )
            ),
        }
