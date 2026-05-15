import unittest
from unittest.mock import patch

from app.services import serial_tnc


class _FakeOsNoCloexec:
    O_RDWR = 0x01
    O_NOCTTY = 0x02
    O_NONBLOCK = 0x04

    def __init__(self) -> None:
        self.open_calls: list[tuple[str, int]] = []
        self.close_calls: list[int] = []

    def open(self, path: str, flags: int) -> int:
        self.open_calls.append((path, flags))
        return 27

    def close(self, fd: int) -> None:
        self.close_calls.append(fd)


class SerialTncLowLevelTests(unittest.TestCase):
    def _termios_attributes(self) -> list[object]:
        cc = [0] * 32
        cc[serial_tnc.termios.VMIN] = 0
        cc[serial_tnc.termios.VTIME] = 0
        return [0, 0, 0, 0, 0, 0, cc]

    def test_normalize_serial_baud_rate_accepts_supported_values(self) -> None:
        for value in sorted(serial_tnc.SUPPORTED_SERIAL_BAUD_RATES):
            self.assertEqual(serial_tnc.normalize_serial_baud_rate(str(value)), value)

    def test_normalize_serial_baud_rate_rejects_unsupported_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be one of"):
            serial_tnc.normalize_serial_baud_rate("12345")

    def test_close_serial_device_default_does_not_drop_modem_lines(self) -> None:
        with patch.object(serial_tnc.os, "close") as close_mock:
            with patch.object(serial_tnc, "_best_effort_set_modem_lines") as modem_lines_mock:
                serial_tnc.close_serial_device(123, drain_timeout=0, flush_buffers=False)
        modem_lines_mock.assert_not_called()
        close_mock.assert_called_once_with(123)

    def test_close_serial_device_with_drop_control_lines_drops_dtr_rts(self) -> None:
        with patch.object(serial_tnc.os, "close") as close_mock:
            with patch.object(serial_tnc, "_best_effort_set_modem_lines") as modem_lines_mock:
                serial_tnc.close_serial_device(123, drain_timeout=0, flush_buffers=False, drop_control_lines=True)
        modem_lines_mock.assert_called_once_with(123, dtr=False, rts=False)
        close_mock.assert_called_once_with(123)

    def test_read_serial_chunk_returns_empty_bytes_when_select_interrupted(self) -> None:
        with patch.object(serial_tnc.select, "select", side_effect=InterruptedError):
            self.assertEqual(serial_tnc.read_serial_chunk(7, timeout=0.1), b"")

    def test_write_serial_data_uses_deadline_for_whole_operation(self) -> None:
        monotonic_values = iter([0.0, 0.0, 0.6, 1.1])
        with patch.object(serial_tnc.time, "monotonic", side_effect=lambda: next(monotonic_values)):
            with patch.object(serial_tnc.select, "select", return_value=([], [17], [])) as select_mock:
                with patch.object(serial_tnc.os, "write", return_value=1) as write_mock:
                    with self.assertRaisesRegex(TimeoutError, "Serial write timed out\\."):
                        serial_tnc.write_serial_data(17, b"abc", timeout=1.0, drain=False)

        self.assertEqual(write_mock.call_count, 2)
        timeouts = [float(item.args[3]) for item in select_mock.call_args_list]
        self.assertEqual(len(timeouts), 2)
        self.assertAlmostEqual(timeouts[0], 1.0)
        self.assertLess(timeouts[1], timeouts[0])

    def test_write_serial_data_retries_after_interrupted_select(self) -> None:
        monotonic_values = iter([10.0, 10.0, 10.1])
        with patch.object(serial_tnc.time, "monotonic", side_effect=lambda: next(monotonic_values)):
            with patch.object(serial_tnc.select, "select", side_effect=[InterruptedError(), ([], [23], [])]) as select_mock:
                with patch.object(serial_tnc.os, "write", return_value=3) as write_mock:
                    serial_tnc.write_serial_data(23, b"abc", timeout=1.0, drain=False)
        self.assertEqual(select_mock.call_count, 2)
        write_mock.assert_called_once_with(23, b"abc")

    def test_open_serial_device_adds_cloexec_when_available_and_disables_crtscts(self) -> None:
        attributes = self._termios_attributes()
        captured: dict[str, list[object]] = {}
        events: list[str] = []

        def fake_setattr(_fd: int, _when: int, updated: list[object]) -> None:
            events.append("setattr")
            captured["attrs"] = [
                updated[0],
                updated[1],
                updated[2],
                updated[3],
                updated[4],
                updated[5],
                list(updated[6]),
            ]

        def fake_flush(_fd: int, _queue: int) -> None:
            events.append("flush")

        with patch.object(serial_tnc.os, "O_CLOEXEC", 0x400000, create=True):
            with patch.object(serial_tnc.os, "open", return_value=19) as open_mock:
                with patch.object(serial_tnc.termios, "tcgetattr", return_value=attributes):
                    with patch.object(serial_tnc.termios, "tcsetattr", side_effect=fake_setattr):
                        with patch.object(serial_tnc.termios, "tcflush", side_effect=fake_flush):
                            fd = serial_tnc.open_serial_device("/dev/ttyUSB0", 9600, flush_buffers=True)

        self.assertEqual(fd, 19)
        open_args = open_mock.call_args.args
        self.assertEqual(open_args[0], "/dev/ttyUSB0")
        self.assertTrue(int(open_args[1]) & 0x400000)
        self.assertEqual(events, ["setattr", "flush"])

        applied = captured["attrs"]
        self.assertEqual(applied[0], 0)
        self.assertEqual(applied[1], 0)
        self.assertEqual(applied[3], 0)
        cflag = int(applied[2])
        self.assertTrue(cflag & int(serial_tnc.termios.CLOCAL))
        self.assertTrue(cflag & int(serial_tnc.termios.CREAD))
        self.assertTrue(cflag & int(serial_tnc.termios.CS8))
        self.assertFalse(cflag & int(getattr(serial_tnc.termios, "PARENB", 0)))
        self.assertFalse(cflag & int(getattr(serial_tnc.termios, "CSTOPB", 0)))
        if hasattr(serial_tnc.termios, "CRTSCTS"):
            self.assertFalse(cflag & int(serial_tnc.termios.CRTSCTS))

    def test_open_serial_device_works_without_cloexec_flag(self) -> None:
        fake_os = _FakeOsNoCloexec()
        with patch.object(serial_tnc, "os", fake_os):
            with patch.object(serial_tnc.termios, "tcgetattr", return_value=self._termios_attributes()):
                with patch.object(serial_tnc.termios, "tcsetattr"):
                    fd = serial_tnc.open_serial_device("/dev/ttyUSB1", 9600, flush_buffers=False)

        self.assertEqual(fd, 27)
        self.assertEqual(fake_os.open_calls, [("/dev/ttyUSB1", 0x01 | 0x02 | 0x04)])


if __name__ == "__main__":
    unittest.main()
