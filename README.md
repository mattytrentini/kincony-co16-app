# KinCony CO16 application

MicroPython application for the [KinCony CO16](https://www.kincony.com/esp32-s3-16-channel-analog-input-smart-controller.html), using [Microdot](https://github.com/miguelgrinberg/microdot) for an asynchronous HTTP server.

The application serves a browser dashboard and a versioned JSON REST API.
Relay states are clickable controls for the 16 active-low relay outputs;
the 16 digital inputs remain read-only. The dashboard also displays the
on-board DS3231 clock. The LCD shows a MicroPython splash followed by a live,
read-only status screen. Input configuration is unchanged; ADCs and optional
modules are not initialized. Ethernet uses the built-in W5500 driver on SPI1;
the LCD uses shared SPI2.

## Requirements

- Assumes the appropriate [KINCONY_CO16 MicroPython firmware](https://github.com/mattytrentini/micropython/tree/kincony-co16/ports/esp32/boards/KINCONY_CO16)
  is already installed.
- An Ethernet connection to a LAN with DHCP. HTTP listens on port **80**;
  no WiFi credentials or secrets are stored in this repository.

This is an **unauthenticated, unencrypted, trusted-LAN interface**. Anyone with
network access can switch physical relay outputs and set the clock. Do not
expose it directly to the Internet; check attached equipment before switching.

## Install

Connect the board over USB, then install the application and all dependencies:

```sh
mpremote mip install github:mattytrentini/kincony-co16-app
```

If needed, install `mpremote` with:

```sh
uv tool install mpremote
```

The manifest installs modules and browser assets into `/lib` and the boot entry
point into `/main.py`. No clone, Docker container, or separate file copy is
required. Installation replaces any existing `/main.py`; back it up first if
you need to keep it.

Reset the board after installation. `main.py` enables Ethernet DHCP and starts
the LCD task alongside Microdot's `await app.start_server(host="0.0.0.0", port=80)`.
The HTTP server can start before DHCP completes and is accessible once an
address is assigned. Find that address on the LCD or in your DHCP server's
lease list, then open `http://BOARD_IP/`.
To stop the app and return to the REPL, interrupt it with Ctrl-C.

### Dependencies

`package.json` pins the verified driver and Microdot revisions for reproducible
installation:

- [PCF8575](https://github.com/mcauser/micropython-pcf8575)
- [XL9535 / XL9555](https://github.com/mattytrentini/micropython-xl9535)
- [ADS1x15](https://github.com/robert-hh/ads1x15)
- [DS3231](https://github.com/mattytrentini/micropython-DS3231-AT24C32)
- [ST7789, CO16 display configuration and 8x16 font](https://github.com/mattytrentini/st7789py_mpy)
- [Microdot](https://github.com/miguelgrinberg/microdot), installed as its standalone
  base module; no framework extensions are required.

The DS3231 is read without setting its time on startup. ADC drivers are installed
but are not initialized by this app.
Update dependency pins deliberately when adopting a new driver revision.

## LCD

The landscape 320x240 display shows the MicroPython logo for two seconds, then
refreshes the following information approximately once per second:

- Ethernet connection and IPv4 address.
- Free heap, CPU frequency, application uptime, app and MicroPython versions.
- DS3231 date/time and oscillator validity (`UNTRUSTED` if the clock has lost
  confidence in its time; no automatic clock setting).
- All 16 relay control readbacks and 16 digital inputs, numbered 01–16 in row
  order. `+` means ON/active, `-` means OFF/idle; counts show the active total.

The LCD is strictly read-only: it never switches relays, configures the input
expander, sets the RTC, or initializes ADCs. Relay indications are control-pin
readbacks, **not independent relay-contact feedback**. Use the existing browser
dashboard or REST API for control.

Failed IO reads replace every channel with `?` and the totals with `--/16`,
rather than showing stale values or treating failure as OFF. Clock and system
status failures are shown independently. A fatal display initialization or
rendering error is logged to the REPL and stops only the LCD task; HTTP remains
available. Interrupting the app also cancels its LCD task.

LCD wiring is supplied by the existing CO16 driver configuration: SPI2 SCK=11,
MOSI=10, MISO=12; CS=4, DC=0, reset=5, backlight=40. Other SPI2 chip-selects
(9, 14, 13) are held inactive. Do not initialize native SDCard on the same SPI
host while the LCD is active. The optional LoRa module also shares GPIO5/40
and cannot be used with this display configuration.

The [MicroPython logo](https://commons.wikimedia.org/wiki/File:MicroPython_new_logo.svg)
is copyright Micropython.org, MIT/Expat licensed; its rectangular vector strokes
are scaled and inverted for the dark background. Attribution and the permission
notice are preserved in `co16_lcd.py`. The ST7789 driver and bundled font retain
their upstream MIT license.

## Unix simulation without hardware

The [KinCony simulator](https://github.com/mattytrentini/kincony-sim) runs this
same application, original I2C/SPI drivers and LCD font on the published stock
MicroPython Unix Docker image:

```sh
git clone https://github.com/mattytrentini/kincony-sim.git
cd kincony-sim
git submodule update --init lib/kincony_co16
./sim prepare
./sim co16
```

Open `http://127.0.0.1:8081/` for this dashboard and relay controls, `/display/`
for the live 320×240 LCD, and `/sim/` for sixteen external input stimuli,
configuration/polarity faults, RTC OSF and per-device bus failures. Clock setting
uses the original `POST /api/v1/time` API below; the dashboard displays clock
readback but has no clock editor. All outputs/time writes still use real drivers.
N30 and CO16 can coexist on default host ports 8080 and 8081 respectively.

The device models are reusable, MIT-licensed
[micropython-sim-devices](https://github.com/mattytrentini/micropython-sim-devices)
components; selected PCF8575, XL9535, DS3231 and ST7789/config/font drivers retain
their upstream MIT licenses. A fresh session resets relay signals to OFF and
input configuration to all-input. Native monotonic ticks drive a clearly
synthetic timezone-naive RTC, never the browser clock. Simulated control levels
do not prove physical relay-contact behavior or electrical safety.

`CO16(identity_provider=...)` supplies explicit Unix identity; default hardware
construction still calls native `os.uname()`. `main.main()` accepts optional
board/app/server resources while retaining original workers and port-80 defaults.
The LCD exposes `board.lcd_state` for lifecycle/error observation; drawing code,
driver initialization and GPIO wiring remain unchanged.
No `os`, `time`, `gc`, `framebuf` or firmware-image replacement is needed.

`./sim test-co16` checks actual TCP/driver traffic, all 16 channels, no control
writes on startup/GET/LCD, I2C failures/recovery, RTC/OSF and leap midnight,
RGB565 display/error updates, HTTP during the logo, safe session restart and
HTTP survival after a fatal LCD initialization error. These Unix changes have
not been reflashed or re-tested on physical hardware.

## HTTP interface

`GET /` serves the dashboard. It shows the board and firmware, network state,
IP address, available heap, channel states and the DS3231's wall-clock time.
It refreshes every five seconds and also has a manual **Refresh** button.
Click a relay state to switch that channel; inputs are display-only. Relay
buttons are disabled until a successful IO read and while a request is pending
or IO data is stale. Writes are never automatically retried; an unsuccessful
write may already have changed the output, so the page re-reads the hardware.

Status, IO and clock reads have independent freshness/error reporting. Clock
values are board samples, not the browser's clock or a simulated ticking clock.
An oscillator-stop flag marks the RTC time as untrusted until explicitly set.
The page has no external assets or framework dependencies.

Only the fixed `/assets/app.css` and `/assets/app.js` resources are served;
there is no arbitrary filesystem-serving route.

## REST API

All API responses are JSON with `Cache-Control: no-store`. Readable resources
support `GET` and `HEAD`; relay and clock resources also support `POST`.
Unsupported methods return `405` with a route-specific `Allow` header.
Unknown API routes return `404`. Writes require `Content-Type: application/json`;
malformed or invalid bodies return `400`, and other content types return `415`.

### `GET /api/v1/status`

Returns:

- `app.name`, `app.version`
- `device.model`, `device.firmware`
- `heap_free_bytes`
- `network.interface`, `network.connected`, `network.ipv4`

### `GET /api/v1/io`

Returns two channel groups:

- `relays.raw`: the 16-bit PCF8575 control-level readback.
- `relays.on`: 16 booleans, interpreting active-low control levels.
- `inputs.raw`: the physical input levels, with XL9555 hardware polarity
  inversion removed.
- `inputs.active`: 16 booleans, interpreting the CO16's active-low inputs.

Array index 0 is channel 1, index 15 is channel 16. Relay readback is a control
signal observation, **not relay-contact feedback or a desired output latch**.
Input/relay reads are sequential hardware operations, not a simultaneous sample.
The application preserves existing register settings and requires the XL9555
configuration to be all-input (`0xffff`); it does not silently reconfigure it.

An I2C failure or incompatible input configuration returns `503`:

```json
{"error":{"code":"io_unavailable","message":"IO snapshot is unavailable."}}
```

### `GET` / `POST /api/v1/relays/{channel}`

Channels are numbered **1–16**; other channel numbers return `404`. A GET
returns `{"channel":1,"on":false}`. POST an explicit target state:

```json
{"on":true}
```

`on` must be a JSON boolean, not `0`, `1` or a string. A successful POST returns
the same resource shape with hardware control-level readback. The operation
preserves the other 15 relay bits and does not change input configuration.
It sets an absolute state, not a server-side toggle. I2C failures return `503`;
a failed response does not prove that the write did not happen.

### `GET` / `POST /api/v1/time`

Returns the DS3231 clock:

```json
{"datetime":"2026-10-06T14:32:00","valid":true,"source":"ds3231"}
```

`valid` is false when the oscillator-stop flag is set. The timestamp contains
the RTC's wall-clock fields with **no timezone conversion or implied UTC**.
The application does not automatically set or synchronize the clock.

To set it, POST:

```json
{"datetime":"2026-10-06T14:32:00"}
```

Use exactly `YYYY-MM-DDTHH:MM:SS`, a valid Gregorian date in **2000–2099**,
and 24-hour time. Weekday is calculated; a successful set clears the oscillator-
stop flag and returns the clock resource. RTC I2C failures return `503`.

API errors use the same `error.code` / `error.message` structure. Unexpected
errors are logged on the serial console and return a generic `500`, without
exposing exception text in HTTP responses.

```sh
curl http://BOARD_IP/api/v1/status
curl http://BOARD_IP/api/v1/io
curl http://BOARD_IP/api/v1/time
curl -X POST http://BOARD_IP/api/v1/relays/1 \
  -H 'Content-Type: application/json' -d '{"on":false}'
curl -X POST http://BOARD_IP/api/v1/time \
  -H 'Content-Type: application/json' -d '{"datetime":"2026-10-06T14:32:00"}'
```

## Verification

The application modules were compiled with `mpy-cross` and exercised on the
CO16 through real TCP HTTP requests: status/IO snapshots, relay GET/POST,
DS3231 query/set roundtrip, HEAD, malformed bodies, channel/date boundaries,
content types, route-specific method rejection and actual I2C failures (`503`).
Hardware relay POSTs requested OFF on channels 1 and 16; the whole bank remained
`0xffff`, and the input configuration remained `0xffff`. No relay was energized.

Installed PCF8575 and DS3231 drivers were also exercised against an in-memory
register bus: all 16 active-low relay bits and unrelated-bit preservation,
strict booleans, leap dates, weekday calculation, RTC tuple ordering and
oscillator/status-bit preservation. Physical relay ON transitions were not
exercised.

Desktop and 390-pixel-wide browser views were checked over the board's temporary
Wi-Fi connection. Click and keyboard controls issued real OFF POSTs; browser-
only seeded ON readbacks allowed these checks without energizing outputs.
Pending/double-activation protection, failed-write readback recovery,
independent clock/IO failures and oscillator validity were exercised. All
temporary browser interception was removed afterward.

Default-target mip installation was checked with `/main.py` absent: it created
the root boot entry point and installed all dependencies without a separate
file copy.

Normal boot remains Ethernet DHCP. Ethernet LAN access was not verified;
the browser checks used a RAM-only Wi-Fi session, with no Wi-Fi boot
configuration or stored credentials.

The v0.3.0 LCD addition was compiled with `mpy-cross` and exercised using the
production ST7789 driver and font against a 320x240 SPI display model.
Rendered splash/status/error screens were visually inspected. Checks covered
channel ordering, clearing stale IO after failed reads, recovery, invalid RTC
indication, independent resource failures, and LCD task cancellation.
A real CPython Microdot HTTP server responded during the splash and after an
injected LCD initialization failure. No relay-control methods were called.

The update was subsequently installed and exercised on the CO16 itself.
On-device loopback HTTP requests covered status, IO, time and dashboard HTML,
including a request during the logo splash. Two live LCD refreshes and
cancellation with the main task passed. Relay readback and input configuration
both remained `0xffff`; no relay-control methods or RTC setters were called.
Uninstrumented rendering took approximately 153ms for system status, 67ms for
the clock, and 247/255ms for the initial relay/input grids.

Splash and dashboard pixel streams sent to the real ST7789 were captured; the
reconstructed dashboard was visually inspected. These are not photographs of
the panel, so physical appearance still requires an on-device visual check.
Ethernet had no link during this run, so HTTP was checked over device loopback,
not an external LAN connection. The DS3231 returned an invalid/2000 date with
its oscillator-stop flag set; the LCD correctly showed `UNTRUSTED`. Its time
and validity flag were left unchanged.

## Layout

- `main.py`: MicroPython boot entry point and async server startup.
- `co16.py`: network setup, relay control/readback, input snapshots and DS3231 clock.
- `co16_web.py`: async routes and API error responses.
- `co16_lcd.py`: logo splash and read-only live LCD status task.
- `co16_static/`: HTML, CSS and JavaScript dashboard.
- `package.json`: application assets and pinned mip dependencies.

MIT license; copyright 2026 Matt Trentini. Dependency licenses remain with their
respective upstream projects.
