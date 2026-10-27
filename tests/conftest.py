import os
import sys
from pathlib import Path
import pytest

ROOT = Path(r"E:\QQAgent")
TEST = ROOT / "runtime" / "test-state"
TEST.mkdir(parents=True, exist_ok=True)
for directory in ("tmp", "framework-root/data/astrbot/data"):
    (TEST / directory).mkdir(parents=True, exist_ok=True)
os.environ.update(
    PYTHONDONTWRITEBYTECODE="1",
    QQAGENT_ROOT=str(TEST / "framework-root"),
    ASTRBOT_ROOT=str(TEST / "framework-root" / "data" / "astrbot"),
    NAPCAT_WORKDIR=str(TEST / "napcat"),
    TEMP=str(TEST / "tmp"),
    TMP=str(TEST / "tmp"),
)
sys.path[:0] = [str(ROOT), str(ROOT / "app" / "AstrBot"), str(ROOT / "tests")]
from scripts.configure import save_configuration
from plugins.mansui_companion.settings import Settings

save_configuration(
    TEST / "framework-root",
    Settings(
        "10001",
        "90001",
        ("80001", "80002"),
        ready=True,
        deepseek_api_key="TEST_ONLY_NOT_A_REAL_KEY",
        onebot_token="SYNTHETIC_ONEBOT_TOKEN",
        control_token="SYNTHETIC_CONTROL_TOKEN",
    ),
)


@pytest.fixture(autouse=True)
def forbid_external_network(monkeypatch):
    import socket

    original = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in (
            "127.0.0.1",
            "::1",
            "localhost",
        ):
            raise AssertionError("Offline tests must not connect to external services")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
