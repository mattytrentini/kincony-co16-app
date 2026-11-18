# Copyright (c) 2026 Matt Trentini
# MicroPython logo copyright (c) Micropython.org; MIT/Expat license.
# Logo source: https://commons.wikimedia.org/wiki/File:MicroPython_new_logo.svg
# Adaptation: scaled to 112x112 and inverted for a dark LCD background.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Read-only 320x240 LCD companion to the CO16 HTTP application."""

import asyncio
import sys
import time

import machine

BG = 0x0841
HEADER = 0x10E4
TEXT = 0xFFFF
MUTED = 0xAD75
ACCENT = 0x35FB
RELAY_ON = 0x0280
INPUT_ACTIVE = 0x03AE
OFF = 0x18E3
WARNING = 0xFD20
ERROR = 0xF986


class LCD:
    def __init__(self, tft, font):
        self.tft = tft
        self.font = font
        self._previous = {}

    def _text(self, text, x, y, color=TEXT, background=BG):
        self.tft.text(self.font, text[: (320 - x) // 8], x, y, color, background)

    def _field(self, text, x, y, width, color=TEXT, background=BG):
        self.tft.fill_rect(x, y, width, 16, background)
        self._text(text[: width // 8], x, y, color, background)

    def splash(self):
        self.tft.fill(BG)
        # The linked vector consists only of rectangular strokes and an eye.
        for x, y, width, height in (
            (0, 0, 12, 56), (15, 0, 12, 56), (29, 0, 12, 56),
            (44, 0, 12, 56), (12, 0, 3, 12), (27, 44, 2, 12),
            (41, 0, 3, 12),
        ):
            self.tft.fill_rect(104 + 2 * x, 24 + 2 * y, 2 * width, 2 * height, TEXT)
        self.tft.fill_rect(202, 116, 6, 10, BG)
        self._text("MicroPython", 116, 156)
        self._text("KinCony CO16", 112, 184, ACCENT)

    def layout(self):
        self.tft.fill(BG)
        self.tft.fill_rect(0, 0, 320, 26, HEADER)
        self._text("KinCony CO16", 8, 5, TEXT, HEADER)
        self.tft.hline(0, 26, 320, ACCENT)

    def status(self, snapshot, uptime_s):
        if snapshot is None:
            connection, address, heap, version, firmware = (
                "Status unavailable", "IP --", "Heap --", "", "MP --"
            )
        else:
            net = snapshot["network"]
            interface = "ETH" if net["interface"] == "ethernet" else net["interface"]
            connection = interface + (": online" if net["connected"] else ": waiting")
            address = "IP " + net["ipv4"] if net["connected"] else "IP --"
            heap = "%.1fM free" % (snapshot["heap_free_bytes"] / 1048576)
            version = "v" + snapshot["app"]["version"]
            firmware = "MP" + snapshot["device"]["firmware"].split("-", 1)[0].lstrip("v")
        self._field(version, 256, 5, 56, MUTED, HEADER)
        self._field(connection, 8, 32, 224, ACCENT if snapshot else ERROR)
        self._field("CPU %dM" % (machine.freq() // 1000000), 240, 32, 72, MUTED)
        self._field(address, 8, 50, 224)
        self._field(heap, 240, 50, 72, MUTED)
        days, seconds = divmod(uptime_s, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        self._field("Up %dd %02d:%02d:%02d" % (days, hours, minutes, seconds), 8, 86, 224, MUTED)
        self._field(firmware, 240, 86, 72, MUTED)

    def clock(self, snapshot):
        text = snapshot["datetime"].replace("T", " ") if snapshot is not None else "Clock unavailable"
        if snapshot is None:
            state, color = "RTC ERROR", ERROR
        elif snapshot["valid"]:
            state, color = "RTC OK", ACCENT
        else:
            state, color = "UNTRUSTED", WARNING
        self._field(text, 8, 68, 224)
        self._field(state, 240, 68, 72, color)

    def channels(self, name, values, y):
        values = tuple(values) if values is not None else None
        if name in self._previous and self._previous[name] == values:
            return
        previous = self._previous.get(name)
        self._previous[name] = values
        label = "RELAYS +=ON -=OFF" if name == "RELAYS" else "INPUTS +=ACTIVE -=IDLE"
        self._field(label, 8, y, 304, ERROR if values is None else TEXT)
        self._text("--/16" if values is None else "%d/16" % sum(values), 272, y)
        for index in range(16):
            if previous is not None and values is not None and previous[index] == values[index]:
                continue
            value = values[index] if values is not None else None
            x, top = 8 + index % 8 * 38, y + 19 + index // 8 * 23
            color = (RELAY_ON if name == "RELAYS" else INPUT_ACTIVE) if value else OFF
            self.tft.fill_rect(x, top, 34, 20, color)
            self.tft.rect(x, top, 34, 20, ERROR if value is None else MUTED)
            marker = "?" if value is None else "+" if value else "-"
            self._text("%02d%s" % (index + 1, marker), x + 5, top + 2, TEXT, color)


async def run(board):
    """Run beside HTTP; sample status, IO and RTC without any control writes.

    Each resource has independent unavailable reporting. Fatal LCD errors are
    logged and stop only this task, not the HTTP server. No automatic retry.
    """
    board.lcd_state = "starting"
    try:
        import co16_tft_config
        import vga1_8x16

        previous = time.ticks_ms()
        elapsed_ms = 0
        lcd = LCD(co16_tft_config.config(), vga1_8x16)
        board.lcd_state = "running"
        lcd.splash()
        await asyncio.sleep_ms(2000)
        lcd.layout()
        while True:
            now = time.ticks_ms()
            elapsed_ms += time.ticks_diff(now, previous)
            previous = now
            try:
                status = board.status()
            except OSError:
                status = None
            lcd.status(status, elapsed_ms // 1000)
            await asyncio.sleep_ms(0)
            try:
                clock = board.clock()
            except OSError:
                clock = None
            lcd.clock(clock)
            await asyncio.sleep_ms(0)
            try:
                snapshot = board.io()
            except OSError:
                snapshot = None
            lcd.channels("RELAYS", snapshot["relays"]["on"] if snapshot else None, 109)
            await asyncio.sleep_ms(0)
            lcd.channels("INPUTS", snapshot["inputs"]["active"] if snapshot else None, 177)
            await asyncio.sleep_ms(1000)
    except Exception as error:
        board.lcd_state = "unavailable"
        print("CO16 LCD stopped; HTTP service remains available:")
        sys.print_exception(error)
    finally:
        if board.lcd_state != "unavailable":
            board.lcd_state = "stopped"
