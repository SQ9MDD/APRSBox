from __future__ import annotations

import array
import fcntl
import os
import select
import termios
import time

SUPPORTED_SERIAL_BAUD_RATES: dict[int, int] = {
    value: getattr(termios, f"B{value}")
    for value in (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)
    if hasattr(termios, f"B{value}")
}


def normalize_serial_device_path(value: object, *, label: str = "Serial device path") -> str:
    path = str(value or "").strip()
    if not path:
        raise ValueError(f"{label} is required for serial TNC.")
    return path


def normalize_serial_baud_rate(value: object, *, label: str = "Baud rate") -> int:
    try:
        baud_rate = int(str(value or "").strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be one of: {', '.join(str(item) for item in sorted(SUPPORTED_SERIAL_BAUD_RATES))}.") from exc
    if baud_rate not in SUPPORTED_SERIAL_BAUD_RATES:
        raise ValueError(f"{label} must be one of: {', '.join(str(item) for item in sorted(SUPPORTED_SERIAL_BAUD_RATES))}.")
    return baud_rate


def open_serial_device(path: str, baud_rate: int, *, flush_buffers: bool = True) -> int:
    normalized_path = normalize_serial_device_path(path)
    normalized_baud_rate = normalize_serial_baud_rate(baud_rate)
    fd = os.open(normalized_path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        attributes = termios.tcgetattr(fd)
        attributes[0] = 0
        attributes[1] = 0
        attributes[2] = termios.CLOCAL | termios.CREAD | termios.CS8
        attributes[3] = 0
        attributes[6][termios.VMIN] = 1
        attributes[6][termios.VTIME] = 0
        speed = SUPPORTED_SERIAL_BAUD_RATES[normalized_baud_rate]
        attributes[4] = speed
        attributes[5] = speed
        if flush_buffers:
            termios.tcflush(fd, termios.TCIOFLUSH)
        termios.tcsetattr(fd, termios.TCSANOW, attributes)
    except Exception:
        os.close(fd)
        raise
    return fd


def close_serial_device(
    fd: int | None,
    *,
    drain_timeout: float = 0.2,
    flush_buffers: bool = True,
    drop_control_lines: bool = True,
) -> None:
    if fd is None:
        return
    if drain_timeout > 0:
        try:
            _best_effort_drain(fd, timeout=drain_timeout)
        except OSError:
            pass
    if flush_buffers:
        try:
            termios.tcflush(fd, termios.TCIOFLUSH)
        except OSError:
            pass
    if drop_control_lines:
        _best_effort_set_modem_lines(fd, dtr=False, rts=False)
    try:
        os.close(fd)
    except OSError:
        pass


def read_serial_chunk(fd: int, *, max_bytes: int = 1024, timeout: float = 1.0) -> bytes:
    readable, _, _ = select.select([fd], [], [], timeout)
    if not readable:
        return b""
    try:
        return os.read(fd, max_bytes)
    except BlockingIOError:
        return b""


def write_serial_data(fd: int, data: bytes, *, timeout: float = 1.0, drain: bool = False) -> None:
    offset = 0
    while offset < len(data):
        _, writable, _ = select.select([], [fd], [], timeout)
        if not writable:
            raise TimeoutError("Serial write timed out.")
        try:
            written = os.write(fd, data[offset:])
        except BlockingIOError:
            continue
        if written <= 0:
            raise OSError("Serial write failed.")
        offset += written
    if drain:
        _best_effort_drain(fd, timeout=timeout)


def _best_effort_drain(fd: int, *, timeout: float) -> None:
    # Prefer a bounded drain strategy to avoid indefinite blocking on pseudo terminals
    # and edge-case drivers.
    tiocoutq = getattr(termios, "TIOCOUTQ", None)
    if tiocoutq is None:
        return

    deadline = time.monotonic() + max(0.05, float(timeout))
    pending = array.array("i", [0])
    while time.monotonic() < deadline:
        try:
            fcntl.ioctl(fd, tiocoutq, pending, True)
        except OSError:
            return
        if pending[0] <= 0:
            return
        time.sleep(0.01)


def _best_effort_set_modem_lines(fd: int, *, dtr: bool | None, rts: bool | None) -> None:
    tiocmbic = getattr(termios, "TIOCMBIC", None)
    tiocmbis = getattr(termios, "TIOCMBIS", None)
    dtr_mask = getattr(termios, "TIOCM_DTR", None)
    rts_mask = getattr(termios, "TIOCM_RTS", None)
    if tiocmbic is None or tiocmbis is None:
        return

    clear_mask = 0
    set_mask = 0
    if dtr is not None and dtr_mask is not None:
        if dtr:
            set_mask |= int(dtr_mask)
        else:
            clear_mask |= int(dtr_mask)
    if rts is not None and rts_mask is not None:
        if rts:
            set_mask |= int(rts_mask)
        else:
            clear_mask |= int(rts_mask)

    if clear_mask:
        try:
            clear_bits = array.array("i", [clear_mask])
            fcntl.ioctl(fd, tiocmbic, clear_bits, True)
        except OSError:
            return
    if set_mask:
        try:
            set_bits = array.array("i", [set_mask])
            fcntl.ioctl(fd, tiocmbis, set_bits, True)
        except OSError:
            return
