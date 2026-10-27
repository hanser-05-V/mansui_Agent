from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class AffinityState:
    score: int = 20
    local_day: str = ""
    gained: int = 0
    lost: int = 0
    last_change: float | None = None


def apply_change(
    state: AffinityState, proposal: object, now: datetime
) -> tuple[AffinityState, int]:
    if now.tzinfo is None:
        raise ValueError("timezone_required")
    day = now.astimezone(LOCAL_TZ).date().isoformat()
    current = (
        state
        if state.local_day == day
        else replace(state, local_day=day, gained=0, lost=0)
    )
    if type(proposal) is not int or proposal not in (-1, 0, 1):
        return current, 0
    seconds = now.timestamp()
    if current.last_change is not None and seconds - current.last_change < 600:
        return current, 0
    if proposal > 0 and current.gained >= 3:
        return current, 0
    if proposal < 0 and current.lost >= 3:
        return current, 0
    score = max(0, min(100, current.score + proposal))
    actual = score - current.score
    if not actual:
        return current, 0
    return replace(
        current,
        score=score,
        last_change=seconds,
        gained=current.gained + max(actual, 0),
        lost=current.lost + max(-actual, 0),
    ), actual


def stage(score: int) -> str:
    return (
        "谨慎"
        if score < 25
        else "熟悉"
        if score < 50
        else "信任"
        if score < 75
        else "亲近"
    )
