# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini

import gc
import os

import network
from machine import I2C, Pin, SPI
from ds3231 import DS3231
from pcf8575 import PCF8575
from xl9535 import XL9535

VERSION = "0.2.0"


class CO16:
    """CO16 relay controls, read-only inputs, RTC and Ethernet interface."""

    def __init__(self):
        self.i2c = I2C(0, sda=Pin(8), scl=Pin(18), freq=100_000)
        self._relays = PCF8575(self.i2c, address=0x22)
        self._inputs = XL9535(self.i2c, address=0x24)
        self._rtc = DS3231(self.i2c, addr=0x68)
        self.lan = network.LAN(
            spi=SPI(1, baudrate=16_000_000, polarity=0, phase=0),
            phy_type=network.PHY_W5500,
            phy_addr=0,
            cs=Pin(42),
            int=Pin(43),
            reset=Pin(44),
        )
        identity = os.uname()
        self._model = identity.machine
        self._firmware = identity.version

    def start_network(self):
        """Enable Ethernet; the firmware obtains an address through DHCP."""
        self.lan.active(True)

    def status(self):
        return {
            "app": {"name": "kincony-co16-app", "version": VERSION},
            "device": {"model": self._model, "firmware": self._firmware},
            "heap_free_bytes": gc.mem_free(),
            "network": {
                "interface": "ethernet",
                "connected": self.lan.isconnected(),
                "ipv4": self.lan.ifconfig()[0],
            },
        }

    def io(self):
        """Sample active-low control/input levels without changing registers."""
        if self._inputs.config != 0xFFFF:
            raise OSError("digital input expander is not configured as all inputs")
        relays = self._relays.port
        inputs = self._inputs.input ^ self._inputs.polarity
        return {
            "relays": {
                "raw": relays,
                "on": [not bool(relays & (1 << bit)) for bit in range(16)],
            },
            "inputs": {
                "raw": inputs,
                "active": [not bool(inputs & (1 << bit)) for bit in range(16)],
            },
        }

    def relay(self, channel, on=None):
        """Read or explicitly set one active-low relay, preserving other bits."""
        if type(channel) is not int or not 1 <= channel <= 16:
            raise ValueError("relay channel must be an integer from 1 to 16")
        if on is not None and type(on) is not bool:
            raise ValueError("relay state must be a boolean")
        mask = 1 << (channel - 1)
        port = self._relays.port
        if on is not None:
            # The driver's pin methods use a stale buffer: always fresh-read
            # the whole bank before changing exactly one bit, without awaits.
            self._relays.port = port & ~mask if on else port | mask
            port = self._relays.port
        return {"channel": channel, "on": not bool(port & mask)}

    def clock(self, datetime=None):
        """Read DS3231 wall time/OSF, or validate and explicitly set wall time."""
        if datetime is not None:
            if (
                type(datetime) is not str
                or len(datetime) != 19
                or datetime[4] != "-"
                or datetime[7] != "-"
                or datetime[10] != "T"
                or datetime[13] != ":"
                or datetime[16] != ":"
            ):
                raise ValueError("datetime must be YYYY-MM-DDTHH:MM:SS")
            digits = (
                datetime[:4] + datetime[5:7] + datetime[8:10]
                + datetime[11:13] + datetime[14:16] + datetime[17:19]
            )
            if any(character < "0" or character > "9" for character in digits):
                raise ValueError("datetime must contain ASCII digits")
            year = int(datetime[:4])
            month = int(datetime[5:7])
            day = int(datetime[8:10])
            hour = int(datetime[11:13])
            minute = int(datetime[14:16])
            second = int(datetime[17:19])
            if not (
                2000 <= year <= 2099 and 1 <= month <= 12
                and 0 <= hour <= 23 and 0 <= minute <= 59
                and 0 <= second <= 59
            ):
                raise ValueError("datetime fields are out of range")
            leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            month_days = (31, 29 if leap else 28, 31, 30, 31, 30,
                          31, 31, 30, 31, 30, 31)
            if not 1 <= day <= month_days[month - 1]:
                raise ValueError("datetime day is out of range")
            # Monday=1 through Sunday=7; 2000-01-01 was Saturday.
            years = year - 2000
            days = years * 365 + (years + 3) // 4
            days += sum(month_days[:month - 1]) + day - 1
            weekday = (days + 5) % 7 + 1
            # The driver setter differs from its RTC-compatible getter tuple.
            # Only this explicit write clears OSF, preserving other status bits.
            self._rtc.datetime((year, month, day, hour, minute, second, weekday))
        current = self._rtc.datetime()
        return {
            "datetime": "%04d-%02d-%02dT%02d:%02d:%02d" % (
                current[0], current[1], current[2],
                current[4], current[5], current[6],
            ),
            "valid": not self._rtc.OSF(),
            "source": "ds3231",
        }
