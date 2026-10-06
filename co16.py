# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini

import gc
import os

import network
from machine import I2C, Pin, SPI
from pcf8575 import PCF8575
from xl9535 import XL9535

VERSION = "0.1.0"


class CO16:
    """Read-only IO snapshots and the CO16's Ethernet interface."""

    def __init__(self):
        self.i2c = I2C(0, sda=Pin(8), scl=Pin(18), freq=100_000)
        self._relays = PCF8575(self.i2c, address=0x22)
        self._inputs = XL9535(self.i2c, address=0x24)
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
