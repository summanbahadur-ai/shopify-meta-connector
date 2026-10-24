"""Rate limits and retry suppression, with optional durable D1 storage."""
from collections import OrderedDict
import time
from typing import Protocol


class ButtonState(Protocol):
    durable: bool
    async def allow(self, key: str, limit: int) -> bool: ...
    async def claim(self, key: str, ttl: int) -> bool: ...


class LocalButtonState:
    """Bounded per-process protection; D1 is preferable across Worker isolates."""
    durable = False
    def __init__(self):
        self.windows = OrderedDict()
        self.claims = OrderedDict()

    async def allow(self, key, limit):
        now = time.time()
        count, expiry = self.windows.get(key, (0, now + 60))
        if expiry <= now:
            count, expiry = 0, now + 60
        self.windows[key] = (count + 1, expiry)
        self.windows.move_to_end(key)
        while len(self.windows) > 1024:
            self.windows.popitem(last=False)
        return count < limit

    async def claim(self, key, ttl):
        now = time.time()
        if self.claims.get(key, 0) > now:
            return False
        self.claims[key] = now + ttl
        self.claims.move_to_end(key)
        while len(self.claims) > 1024:
            self.claims.popitem(last=False)
        return True


class D1ButtonState:
    durable = True
    def __init__(self, database):
        self.database = database

    async def allow(self, key, limit):
        now = int(time.time())
        row = await self.database.prepare("""
            INSERT INTO button_webhook_rate (state_key, count, expires_at) VALUES (?, 1, ?)
            ON CONFLICT(state_key) DO UPDATE SET
              count=CASE WHEN expires_at <= ? THEN 1 ELSE count+1 END,
              expires_at=CASE WHEN expires_at <= ? THEN ? ELSE expires_at END
            WHERE expires_at <= ? OR count < ? RETURNING count
        """).bind(key, now + 60, now, now, now + 60, now, limit).first()
        return row is not None

    async def claim(self, key, ttl):
        now = int(time.time())
        row = await self.database.prepare("""
            INSERT INTO button_webhook_claims (state_key, expires_at) VALUES (?, ?)
            ON CONFLICT(state_key) DO UPDATE SET expires_at=excluded.expires_at
            WHERE expires_at <= ? RETURNING state_key
        """).bind(key, now + ttl, now).first()
        return row is not None


local_state = LocalButtonState()
