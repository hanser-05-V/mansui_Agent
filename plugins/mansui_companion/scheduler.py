import asyncio
import time
from collections import deque
from .domain import Route


class Scheduler:
    def __init__(self, process, concurrency=2, capacity=10, on_drop=None):
        self.process = process
        self.concurrency = concurrency
        self.capacity = capacity
        self.on_drop = on_drop or (lambda message, reason: None)
        self.queues = {}
        self.running = {}
        self.closed = False
        self.order = 0
        self.arrivals = {}
        self.ready_at = {}
        self.wakeup = asyncio.Event()
        self.dispatcher = None

    def submit(self, message, route):
        if self.closed:
            return "closed"
        q = self.queues.setdefault(message.scope, deque())
        if len(q) >= self.capacity:
            optional = next((item for item in q if item[1] == Route.OPTIONAL), None)
            if route == Route.REQUIRED and optional:
                q.remove(optional)
                self.on_drop(optional[0], "displaced")
            else:
                return "overloaded"
        self.order += 1
        q.append((message, route, self.order))
        now = time.monotonic()
        previous = self.arrivals.get(message.scope, now - 0.2)
        self.arrivals[message.scope] = now
        if len(q) == 1:
            self.ready_at[message.scope] = (
                now + min(2, max(0.05, (now - previous) * 0.5))
                if route == Route.OPTIONAL
                else now
            )
        if route == Route.REQUIRED:
            self.ready_at[message.scope] = now
        self.wakeup.set()
        if self.dispatcher is None or self.dispatcher.done():
            self.dispatcher = asyncio.create_task(self._dispatch())
        return "queued"

    async def _dispatch(self):
        while self.queues or self.running:
            self.wakeup.clear()
            candidates = [
                s for s, q in self.queues.items() if q and s not in self.running
            ]
            candidates.sort(
                key=lambda s: (
                    not any(i[1] == Route.REQUIRED for i in self.queues[s]),
                    self.queues[s][0][2],
                )
            )
            now = time.monotonic()
            for scope in candidates:
                if len(self.running) >= self.concurrency:
                    break
                if self.ready_at.get(scope, 0) > now:
                    continue
                q = self.queues[scope]
                item = q.popleft()
                if item[1] == Route.OPTIONAL:
                    while q and q[0][1] == Route.OPTIONAL:
                        self.on_drop(item[0], "merged_into:" + q[0][0].message_id)
                        item = q.popleft()
                self.running[scope] = asyncio.create_task(self._work(scope, item))
            if not self.queues and not self.running:
                break
            try:
                await asyncio.wait_for(self.wakeup.wait(), 0.05)
            except TimeoutError:
                pass

    async def _work(self, scope, item):
        try:
            await self.process(item[0], item[1])
        except asyncio.CancelledError:
            self.on_drop(item[0], "shutdown")
            raise
        except Exception:
            self.on_drop(item[0], "worker_failed")
        finally:
            self.running.pop(scope, None)
            if not self.queues.get(scope):
                self.queues.pop(scope, None)
                self.ready_at.pop(scope, None)
                self.arrivals.pop(scope, None)
            self.wakeup.set()

    async def join(self):
        if self.dispatcher:
            await self.dispatcher

    async def close(self, timeout=15):
        self.closed = True
        for scope, q in list(self.queues.items()):
            for message, route, _ in q:
                self.on_drop(message, "shutdown")
            q.clear()
            if scope not in self.running:
                self.queues.pop(scope, None)
        self.wakeup.set()
        try:
            await asyncio.wait_for(asyncio.shield(self.join()), timeout)
        except TimeoutError:
            tasks = list(self.running.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self.dispatcher:
                await self.dispatcher
        self.arrivals.clear()
        self.ready_at.clear()
