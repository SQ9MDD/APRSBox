import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from app.db import init_db
from app.services.aprsis_tx_dispatcher import AprsIsTxDispatcher


class AprsIsTxDispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._previous_db = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(Path(self._temp_dir.name) / "aprsbox-test.db")
        init_db()

    async def asyncTearDown(self) -> None:
        if self._previous_db is None:
            os.environ.pop("APRSBOX_DB_PATH", None)
        else:
            os.environ["APRSBOX_DB_PATH"] = self._previous_db
        self._temp_dir.cleanup()

    async def test_overflow_drops_without_waiting_and_updates_metrics(self) -> None:
        class SlowClient:
            def __init__(self) -> None:
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            async def send_tnc2_line(self, line: str, telemetry=None):
                _ = line, telemetry
                self.started.set()
                await self.release.wait()
                return True, "sent"

        client = SlowClient()
        dispatcher = AprsIsTxDispatcher(client=client, queue_max_frames=1)
        await dispatcher.start()
        try:
            self.assertTrue(dispatcher.enqueue(line="ONE>APRS:>1")[0])
            await asyncio.wait_for(client.started.wait(), timeout=1.0)
            self.assertTrue(dispatcher.enqueue(line="TWO>APRS:>2")[0])
            accepted, detail = dispatcher.enqueue(line="THREE>APRS:>3")
            self.assertFalse(accepted)
            self.assertIn("full", detail)
            metrics = dispatcher.latency_snapshot()
            self.assertEqual(metrics["current_queue_depth"], 1)
            self.assertEqual(metrics["high_water"], 1)
            self.assertEqual(metrics["dropped_overflow"], 1)
            client.release.set()
            await dispatcher.wait_until_idle()
        finally:
            client.release.set()
            await dispatcher.stop()
