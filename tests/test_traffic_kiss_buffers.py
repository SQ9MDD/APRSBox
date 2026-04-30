import unittest

from app.services.traffic import KISS_FEND, _TrafficModemRuntime


class TrafficKissBufferGuardTests(unittest.TestCase):
    def test_rx_kiss_buffer_clears_oversized_unterminated_frame(self) -> None:
        runtime = _TrafficModemRuntime()
        runtime._consume_kiss_chunk(bytes([KISS_FEND, 0x00]))

        for _ in range(12):
            runtime._consume_kiss_chunk(b"A" * 700)

        self.assertEqual(len(runtime._kiss_buffer), 0)

    def test_proxy_uplink_buffer_clears_oversized_unterminated_frame(self) -> None:
        runtime = _TrafficModemRuntime()
        runtime._consume_proxy_uplink_chunk(bytes([KISS_FEND, 0x00]))

        for _ in range(12):
            runtime._consume_proxy_uplink_chunk(b"B" * 700)

        self.assertEqual(len(runtime._proxy_uplink_buffer), 0)


if __name__ == "__main__":
    unittest.main()
