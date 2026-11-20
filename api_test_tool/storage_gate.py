"""One-time PostgreSQL activation gate for a verified storage cutover."""
import asyncio
from contextlib import suppress

from .database import storage_status


class StorageGate:
    def __init__(self):
        self.active = False
        self._activation_task = None

    async def start(self, start_background):
        status = await asyncio.to_thread(storage_status)
        self._validate(status)
        if status['activation'] == 'active':
            start_background()
            self.active = True
        else:
            self._activation_task = asyncio.create_task(self._await_activation(start_background))

    @staticmethod
    def _validate(status):
        if (status.get('backend') != 'postgresql' or status.get('schema') != 1
                or status.get('verified') is not True
                or status.get('activation') not in {'ready', 'active'}):
            raise RuntimeError('PostgreSQL storage has not passed migration verification')

    async def _await_activation(self, start_background):
        # This task exists only between import and the release CLI's durable
        # activation. It exits permanently after starting the original workers.
        while True:
            await asyncio.sleep(1)
            try:
                status = await asyncio.to_thread(storage_status)
                self._validate(status)
            except Exception:
                # A failed status read never opens admission. The health route
                # independently reads storage and exposes the failed readiness.
                continue
            if status['activation'] == 'active':
                start_background()
                self.active = True
                return

    async def close(self):
        if self._activation_task is not None:
            self._activation_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._activation_task
