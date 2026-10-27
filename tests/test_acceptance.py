import asyncio
import tempfile
from pathlib import Path
import pytest
from test_service import Model, raw
from plugins.mansui_companion.settings import Settings
from plugins.mansui_companion.store import Store
from plugins.mansui_companion.service import Service


@pytest.fixture
def components():
    with tempfile.TemporaryDirectory(dir=r"E:\QQAgent\runtime\test-state") as directory:
        store = Store(Path(directory) / "a.sqlite3")
        # This synthetic soak test exercises transactions without physical fsync per message.
        store.db.execute("PRAGMA synchronous=NORMAL")
        model = Model()
        sent = []
        cfg = Settings("10001", "90001", ("80001", "80002"))

        async def send(message, text):
            sent.append((message, text))
            return str(len(sent))

        service = Service(cfg, store, model, send)
        yield service, store, model, sent
        store.close()


async def test_a01_a02_a03_a04_a05_permissions_and_repeat(components):
    service, store, model, sent = components
    for i in range(5):
        service.receive(raw(str(i), group="80001"))
    service.receive(raw("0", group="80001"))
    service.receive(raw("bad", sender="10002"))
    service.receive(raw("outside", group="80003"))
    service.receive(raw("owner-private"))
    service.receive(
        raw(
            "at",
            sender="10002",
            group="80002",
            segments=[
                {"type": "at", "data": {"qq": "90001"}},
                {"type": "text", "data": {"text": "hi"}},
            ],
        )
    )
    await service.join()
    assert len(sent) == 7
    assert store.db.execute("SELECT count(*) FROM events").fetchone()[0] == 7
    assert len(model.calls) == 7
    await service.close()


async def test_a06_a07_a17_natural_participation_and_no_200_limit(components):
    service, store, model, sent = components
    for i in range(202):
        service.receive(raw(str(i), group="80001"))
        await service.join()
    assert len(sent) == 202
    assert sent[-1][0].message_id == "201"
    for i in range(3):
        service.receive(
            raw(
                "other" + str(i),
                sender="10002",
                group="80001",
                text="a continuing new viewpoint",
            )
        )
        await service.join()
    assert len(sent) == 205
    model.answer = {"participate": False, "text": ""}
    service.receive(raw("silent", sender="10002", group="80001"))
    await service.join()
    assert len(sent) == 205
    await service.close()


async def test_a08_a09_a13_model_concurrency_and_fresh_context(components):
    service, store, model, sent = components
    active = 0
    maximum = 0
    original = model.complete

    async def probe(messages, **kw):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep(0.005)
            return await original(messages, **kw)
        finally:
            active -= 1

    model.complete = probe
    service.receive(raw("1", text="PRIVATE_CANARY"))
    service.receive(raw("2", group="80001", text="GROUP_A_CANARY"))
    service.receive(raw("3", group="80002", text="GROUP_B_CANARY"))
    await service.join()
    assert maximum == 2 and active == 0
    for messages, kwargs in model.calls:
        data = messages[-1]["content"]
        assert (
            sum(
                marker in data
                for marker in ("PRIVATE_CANARY", "GROUP_A_CANARY", "GROUP_B_CANARY")
            )
            == 1
        )
    assert service.scheduler.queues == {}
    await service.close()


async def test_a10_a11_a14_recovery_and_queue_overflow_visible(components):
    service, store, model, sent = components
    hold = asyncio.Event()

    async def stalled(messages, **kwargs):
        await hold.wait()
        return '{"participate":true,"text":"ok","affinity_delta":1}'

    model.complete = stalled
    service.receive(raw("first"))
    await asyncio.sleep(0.01)
    for i in range(12):
        service.receive(raw(str(i)))
    assert sum(row["state"] == "overloaded" for row in store.pending()) == 2
    hold.set()
    await service.join()
    assert len(sent) == 11
    assert store.relation(sent[0][0].scope, "10001").score == 21
    await service.close()
