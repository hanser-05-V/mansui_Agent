from dataclasses import dataclass
from enum import Enum
import json


class Route(str, Enum):
    DROP = "drop"
    REQUIRED = "required"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class Message:
    bot: str
    sender: str
    group: str | None
    message_id: str
    text: str
    mentions: frozenset[str]
    received_at: float
    unsupported: bool = False

    @property
    def scope(self) -> str:
        return json.dumps(
            [self.bot, "group" if self.group else "private", self.group or self.sender],
            separators=(",", ":"),
        )

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.bot, self.scope, self.message_id)


@dataclass(frozen=True)
class Reply:
    participate: bool
    text: str
    affinity_delta: int = 0
    affinity_reason: str = ""
    valid: bool = True
