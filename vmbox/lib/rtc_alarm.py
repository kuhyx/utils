#!/usr/bin/env python3
"""Read a stopped guest's CMOS RTC alarm from the host, over QMP.

This is the "did the wake instant survive the guest going down?" probe for
`vm wake`. QEMU keeps a powered-off guest's CMOS alive while the machine sits
in the 'shutdown' runstate (see `qmp.py pause-on-shutdown`), so the alarm the
guest armed with `rtcwake -m no` can be read straight out of the emulated
MC146818 -- not from anything the guest reported about itself.

The alarm registers hold only h:m:s (QEMU's FADT has no day/month alarm:
"alarms up to one day"), so the wake instant is the NEXT time the RTC matches
them -- the same comparison the hardware makes.

Usage:
  rtc_alarm.py read <qmp.sock.ctl>      # JSON report; guest must be stopped
  rtc_alarm.py now <qmp.sock.ctl>       # current RTC as a UTC epoch
  rtc_alarm.py decode <rtc_epoch> <sec> <min> <hour> <reg_b> [<pm1_en>]
                                        # offline decode (unit tests); hex ok
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TextIO

from qmp import command, open_session

REG_B_SET_24H = 0x02
REG_B_BINARY = 0x04
REG_B_AIE = 0x20
PM1_EN_RTC_EN = 0x400
DONT_CARE = 0xC0
# ICH9 ACPI PM I/O base as programmed by both SeaBIOS and OVMF on q35.
PM_BASE = int(os.environ.get("VMBOX_PM_BASE", "0x600"), 0)
CMOS_ALARM_REGS = {"sec": 0x01, "min": 0x03, "hour": 0x05, "reg_b": 0x0B}


@dataclass(frozen=True)
class AlarmReport:
    """Everything `vm wake` needs to decide whether, and when, to power on."""

    rtc_now: datetime
    alarm: datetime | None
    aie: bool
    rtc_en: bool | None
    regs: dict[str, int]

    @property
    def armed(self) -> bool:
        """AIE on and registers decodable: a real board would wake."""
        return self.aie and self.alarm is not None

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready view; epochs are the RTC read as UTC, like rtcwake does."""
        out: dict[str, Any] = {
            "rtc_now": _iso(self.rtc_now),
            "rtc_now_epoch": int(self.rtc_now.timestamp()),
            "aie": self.aie,
            "rtc_en": self.rtc_en,
            "armed": self.armed,
            "regs": {k: f"0x{v:02x}" for k, v in self.regs.items()},
            "alarm": None,
            "alarm_epoch": None,
            "lead_s": None,
        }
        if self.alarm is not None:
            out["alarm"] = _iso(self.alarm)
            out["alarm_epoch"] = int(self.alarm.timestamp())
            out["lead_s"] = int((self.alarm - self.rtc_now).total_seconds())
        return out


def _iso(when: datetime) -> str:
    # The exact shape QEMU's `-rtc base=` accepts.
    return when.strftime("%Y-%m-%dT%H:%M:%S")


def decode_field(raw: int, bcd: bool) -> int | None:
    """One alarm byte; None when it is a don't-care (matches any value)."""
    if raw & DONT_CARE == DONT_CARE:
        return None
    return (raw >> 4) * 10 + (raw & 0x0F) if bcd else raw


def decode_hour(raw: int, bcd: bool, h24: bool) -> int | None:
    """Hour alarm byte, honouring 12-hour mode (bit 7 = PM)."""
    if raw & DONT_CARE == DONT_CARE:
        return None
    if h24:
        return decode_field(raw, bcd)
    value = decode_field(raw & 0x7F, bcd)
    if value is None:
        return None
    return value % 12 + (12 if raw & 0x80 else 0)


def next_match(
    now: datetime, sec: int | None, minute: int | None, hour: int | None
) -> datetime | None:
    """First instant >= now whose h:m:s matches; None if none within a day."""
    start = now.replace(microsecond=0)
    for step in range(24 * 3600 + 1):
        t = start + timedelta(seconds=step)
        if (
            (sec is None or t.second == sec)
            and (minute is None or t.minute == minute)
            and (hour is None or t.hour == hour)
        ):
            return t
    return None


def build_report(
    now: datetime, regs: dict[str, int], pm1_en: int | None
) -> AlarmReport:
    """Decode raw register values into an AlarmReport."""
    reg_b = regs["reg_b"]
    bcd = not reg_b & REG_B_BINARY
    h24 = bool(reg_b & REG_B_SET_24H)
    alarm = next_match(
        now,
        decode_field(regs["sec"], bcd),
        decode_field(regs["min"], bcd),
        decode_hour(regs["hour"], bcd, h24),
    )
    rtc_en = None if pm1_en is None else bool(pm1_en & PM1_EN_RTC_EN)
    return AlarmReport(now, alarm, bool(reg_b & REG_B_AIE), rtc_en, regs)


def _hmp(stream: TextIO, line: str) -> str:
    reply = command(stream, "human-monitor-command", **{"command-line": line})
    if "error" in reply:
        raise SystemExit(f"rtc_alarm: '{line}' failed: {reply['error']}")
    return str(reply.get("return", ""))


def _port_in(stream: TextIO, size: str, port: int) -> int:
    match = re.search(r"=\s*(0x[0-9a-fA-F]+)", _hmp(stream, f"i /{size} 0x{port:x}"))
    if not match:
        raise SystemExit(f"rtc_alarm: unreadable I/O port 0x{port:x}")
    return int(match.group(1), 16)


def _cmos(stream: TextIO, index: int) -> int:
    # Index then data. Never index 0x0C: reading register C clears the flags.
    _hmp(stream, f"o /b 0x70 0x{index:02x}")
    return _port_in(stream, "b", 0x71)


def rtc_now(stream: TextIO) -> datetime:
    """The guest RTC's current value, read as UTC."""
    reply = command(stream, "qom-get", path="/machine", property="rtc-time")
    if "error" in reply:
        raise SystemExit(f"rtc_alarm: cannot read rtc-time: {reply['error']}")
    tm = reply["return"]
    return datetime(
        tm["tm_year"] + 1900,
        tm["tm_mon"] + 1,
        tm["tm_mday"],
        tm["tm_hour"],
        tm["tm_min"],
        tm["tm_sec"],
        tzinfo=UTC,
    )


def read_live(stream: TextIO) -> AlarmReport:
    """Read the alarm out of a STOPPED guest's emulated CMOS."""
    status = command(stream, "query-status").get("return", {})
    if status.get("running"):
        # The CMOS index register is shared with the guest; poking it while
        # the guest runs could corrupt one of its own RTC accesses.
        raise SystemExit("rtc_alarm: guest is running; read only after it stopped")
    regs = {name: _cmos(stream, index) for name, index in CMOS_ALARM_REGS.items()}
    pm1_en = _port_in(stream, "h", PM_BASE + 2)
    return build_report(rtc_now(stream), regs, pm1_en)


def _decode_cli(args: list[str]) -> AlarmReport:
    now = datetime.fromtimestamp(int(args[0]), tz=UTC)
    vals = [int(a, 0) for a in args[1:]]
    regs = dict(zip(("sec", "min", "hour", "reg_b"), vals[:4], strict=True))
    return build_report(now, regs, vals[4] if len(vals) > 4 else None)


def main() -> int:
    argv = sys.argv[1:]
    if argv[:1] == ["decode"] and len(argv) in (6, 7):
        print(json.dumps(_decode_cli(argv[1:]).as_dict()))
        return 0
    if len(argv) != 2 or argv[0] not in ("read", "now"):
        print(__doc__, file=sys.stderr)
        return 2
    if not os.path.exists(argv[1]):
        print(f"rtc_alarm: no such socket: {argv[1]}", file=sys.stderr)
        return 1
    sock, stream = open_session(argv[1])
    try:
        if argv[0] == "now":
            print(int(rtc_now(stream).timestamp()))
        else:
            print(json.dumps(read_live(stream).as_dict()))
    finally:
        stream.close()
        sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
