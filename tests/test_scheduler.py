import asyncio
import unittest
from test_storage import msg, capability
from plugins.mansui_companion.domain import Route


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_fifo_bounded_workers_and_idle_cleanup(self):
        seen = []
        active = 0
        maximum = 0

        async def process(message, route):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.001)
            seen.append((message.scope, message.message_id))
            active -= 1

        q = capability("scheduler").Scheduler(process, concurrency=2, capacity=10)
        for group in ("80001", "80002", "80003"):
            for i in range(5):
                self.assertEqual(q.submit(msg(str(i), group), Route.REQUIRED), "queued")
        await q.join()
        self.assertLessEqual(maximum, 2)
        self.assertEqual(len(seen), 15)
        self.assertEqual(q.queues, {})
        for group in ("80001", "80002", "80003"):
            self.assertEqual(
                [mid for scope, mid in seen if scope == msg(group=group).scope],
                list(map(str, range(5))),
            )
        await q.close()

    async def test_overflow_and_required_displaces_optional(self):
        release = asyncio.Event()
        skipped = []

        async def process(message, route):
            await release.wait()

        q = capability("scheduler").Scheduler(
            process, capacity=2, on_drop=lambda m, r: skipped.append((m.message_id, r))
        )
        q.submit(msg("0"), Route.REQUIRED)
        await asyncio.sleep(0.01)
        q.submit(msg("1"), Route.REQUIRED)
        q.submit(msg("2"), Route.OPTIONAL)
        self.assertEqual(q.submit(msg("3"), Route.REQUIRED), "queued")
        self.assertEqual(q.submit(msg("4"), Route.REQUIRED), "overloaded")
        self.assertIn(("2", "displaced"), skipped)
        release.set()
        await q.join()
        await q.close()

    async def test_failed_scope_does_not_poison_next(self):
        seen = []

        async def process(message, route):
            if message.message_id == "1":
                raise ValueError("fake")
            seen.append(message.message_id)

        q = capability("scheduler").Scheduler(process)
        q.submit(msg("1"), Route.REQUIRED)
        q.submit(msg("2"), Route.REQUIRED)
        await q.join()
        self.assertEqual(seen, ["2"])
        await q.close()
