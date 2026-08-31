import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path

from app.db import execute, fetch_one, init_db
from app.services.rf_tx_dispatcher import RfTxDispatcher


class _FakeTrafficMonitor:
    def __init__(self) -> None:
        self.sent: list[tuple[int, float]] = []

    async def send_outbound_frame(self, *, interface_id: int | None, frame: bytes) -> bool:
        _ = frame
        self.sent.append((int(interface_id or 0), time.monotonic()))
        return True


class RfTxDispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._previous_db = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(Path(self._temp_dir.name) / "aprsbox-test.db")
        init_db()
        for name in ("TNC1", "TNC2"):
            execute(
                """
                INSERT INTO modems(name, modem_type, band, device_path, enabled, notes, created_at, updated_at)
                VALUES (?, 'TCP', '2m', '127.0.0.1:9001', 1, '',
                        '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """,
                (name,),
            )

    async def asyncTearDown(self) -> None:
        if self._previous_db is None:
            os.environ.pop("APRSBOX_DB_PATH", None)
        else:
            os.environ["APRSBOX_DB_PATH"] = self._previous_db
        self._temp_dir.cleanup()

    async def test_digi_jobs_are_ephemeral_and_not_persisted(self) -> None:
        monitor = _FakeTrafficMonitor()
        dispatcher = RfTxDispatcher(traffic_monitor=monitor, min_tx_gap_seconds=0)
        await dispatcher.start()
        try:
            accepted, _detail = dispatcher.enqueue_digi_tx(
                interface_name="TNC1",
                line="SP8ABC>APRS,WIDE1-1:>test",
                frame_uid="ephemeral-1",
            )
            self.assertTrue(accepted)
            await dispatcher.wait_until_idle()
        finally:
            await dispatcher.stop()

        self.assertIsNone(fetch_one("SELECT id FROM outbound_jobs LIMIT 1"))
        self.assertIsNotNone(fetch_one("SELECT id FROM traffic_frames WHERE direction = 'tx' LIMIT 1"))

    async def test_tx_gap_on_tnc1_does_not_block_tnc2(self) -> None:
        monitor = _FakeTrafficMonitor()
        dispatcher = RfTxDispatcher(traffic_monitor=monitor, min_tx_gap_seconds=0.30)
        await dispatcher.start()
        try:
            dispatcher.enqueue_digi_tx(interface_name="TNC1", line="SP8ABC>APRS:>first")
            await dispatcher.wait_until_idle()
            first_tnc1_at = monitor.sent[-1][1]

            dispatcher.enqueue_digi_tx(interface_name="TNC1", line="SP8ABC>APRS:>second")
            dispatcher.enqueue_digi_tx(interface_name="TNC2", line="SP8ABC>APRS:>parallel")
            await asyncio.sleep(0.08)

            tnc2_times = [sent_at for interface_id, sent_at in monitor.sent if interface_id == 2]
            self.assertEqual(len(tnc2_times), 1)
            self.assertLess(tnc2_times[0] - first_tnc1_at, 0.20)
            await dispatcher.wait_until_idle()
        finally:
            await dispatcher.stop()

        tnc1_times = [sent_at for interface_id, sent_at in monitor.sent if interface_id == 1]
        self.assertEqual(len(tnc1_times), 2)
        self.assertGreaterEqual(tnc1_times[1] - tnc1_times[0], 0.28)
