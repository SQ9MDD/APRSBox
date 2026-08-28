import asyncio
import json
import unittest
from unittest.mock import patch

from app.services.traffic_stream import TrafficSnapshotBroadcaster, TrafficStreamCapacityError


class TrafficSnapshotBroadcasterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._log_patch = patch("app.services.traffic_stream.log_event")
        self._log_patch.start()

    def tearDown(self) -> None:
        self._log_patch.stop()

    async def test_broadcaster_runs_single_tick_for_multiple_clients(self) -> None:
        call_count = 0

        def provider() -> dict[str, int]:
            nonlocal call_count
            call_count += 1
            return {"seq": call_count}

        broadcaster = TrafficSnapshotBroadcaster(
            snapshot_provider=provider,
            tick_seconds=0.5,
            heartbeat_seconds=10.0,
            max_clients=4,
        )
        await broadcaster.start()
        try:
            _, queue_a = await broadcaster.subscribe()
            _, queue_b = await broadcaster.subscribe()
            event_a = await asyncio.wait_for(queue_a.get(), timeout=0.8)
            event_b = await asyncio.wait_for(queue_b.get(), timeout=0.8)

            self.assertEqual(event_a, event_b)
            payload = json.loads(event_a[6:].strip())
            self.assertEqual(payload["seq"], 1)
        finally:
            await broadcaster.stop()

    async def test_broadcaster_skips_unchanged_payloads(self) -> None:
        call_count = 0

        def provider() -> dict[str, str]:
            nonlocal call_count
            call_count += 1
            return {"status": "ok"}

        broadcaster = TrafficSnapshotBroadcaster(
            snapshot_provider=provider,
            tick_seconds=0.05,
            heartbeat_seconds=10.0,
            max_clients=4,
        )
        await broadcaster.start()
        try:
            _, queue = await broadcaster.subscribe()
            first_event = await asyncio.wait_for(queue.get(), timeout=0.6)
            self.assertTrue(first_event.startswith("data: "))

            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(queue.get(), timeout=0.25)
            self.assertGreaterEqual(call_count, 2)
        finally:
            await broadcaster.stop()

    async def test_change_token_avoids_rebuilding_unchanged_snapshot(self) -> None:
        snapshot_calls = 0
        token = [1]

        def provider() -> dict[str, int]:
            nonlocal snapshot_calls
            snapshot_calls += 1
            return {"seq": snapshot_calls}

        broadcaster = TrafficSnapshotBroadcaster(
            snapshot_provider=provider,
            change_token_provider=lambda: token[0],
            tick_seconds=0.05,
            heartbeat_seconds=10.0,
            max_clients=4,
        )
        await broadcaster.start()
        try:
            _, queue = await broadcaster.subscribe()
            first_event = await asyncio.wait_for(queue.get(), timeout=0.6)
            self.assertTrue(first_event.startswith("data: "))
            await asyncio.sleep(0.2)
            self.assertEqual(snapshot_calls, 1)

            token[0] = 2
            second_event = await asyncio.wait_for(queue.get(), timeout=0.6)
            self.assertTrue(second_event.startswith("data: "))
            self.assertEqual(snapshot_calls, 2)
        finally:
            await broadcaster.stop()

    async def test_broadcaster_sends_heartbeat(self) -> None:
        def provider() -> dict[str, str]:
            return {"status": "ok"}

        broadcaster = TrafficSnapshotBroadcaster(
            snapshot_provider=provider,
            tick_seconds=0.05,
            heartbeat_seconds=1.0,
            max_clients=4,
        )
        await broadcaster.start()
        try:
            _, queue = await broadcaster.subscribe()
            _ = await asyncio.wait_for(queue.get(), timeout=0.6)
            heartbeat_event = await asyncio.wait_for(queue.get(), timeout=1.6)
            self.assertEqual(heartbeat_event, ": ping\n\n")
        finally:
            await broadcaster.stop()

    async def test_broadcaster_enforces_client_limit(self) -> None:
        broadcaster = TrafficSnapshotBroadcaster(
            snapshot_provider=lambda: {"status": "ok"},
            tick_seconds=0.1,
            heartbeat_seconds=10.0,
            max_clients=1,
        )
        await broadcaster.start()
        try:
            _, _ = await broadcaster.subscribe()
            with self.assertRaises(TrafficStreamCapacityError):
                await broadcaster.subscribe()
        finally:
            await broadcaster.stop()

    async def test_broadcaster_skips_snapshot_without_clients(self) -> None:
        call_count = 0

        def provider() -> dict[str, int]:
            nonlocal call_count
            call_count += 1
            return {"seq": call_count}

        broadcaster = TrafficSnapshotBroadcaster(
            snapshot_provider=provider,
            tick_seconds=0.05,
            heartbeat_seconds=10.0,
            max_clients=4,
        )
        await broadcaster.start()
        try:
            await asyncio.sleep(0.2)
            self.assertEqual(call_count, 0)
        finally:
            await broadcaster.stop()

    async def test_broadcaster_stops_snapshot_after_unsubscribe(self) -> None:
        call_count = 0

        def provider() -> dict[str, int]:
            nonlocal call_count
            call_count += 1
            return {"seq": call_count}

        broadcaster = TrafficSnapshotBroadcaster(
            snapshot_provider=provider,
            tick_seconds=0.05,
            heartbeat_seconds=10.0,
            max_clients=4,
        )
        await broadcaster.start()
        try:
            subscriber_id, queue = await broadcaster.subscribe()
            _ = await asyncio.wait_for(queue.get(), timeout=0.6)
            await broadcaster.unsubscribe(subscriber_id)

            count_after_unsubscribe = call_count
            await asyncio.sleep(0.2)
            self.assertEqual(call_count, count_after_unsubscribe)
        finally:
            await broadcaster.stop()
