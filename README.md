# KinCony CO16 application

MicroPython application for the [KinCony CO16](https://www.kincony.com/esp32-s3-16-channel-analog-input-smart-controller.html), using [Microdot](https://github.com/miguelgrinberg/microdot) for an asynchronous HTTP server.

The application serves a browser dashboard and a versioned JSON REST API.
Relay states are clickable controls for the 16 active-low relay outputs;
the 16 digital inputs remain read-only. The dashboard also displays the
on-board DS3231 clock. Input configuration is unchanged, and LCD, ADCs and
optional modules are not initialized. Ethernet uses the built-in W5500 driver
on SPI1, leaving shared SPI2 peripherals untouched.

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
Microdot with `await app.start_server(host="0.0.0.0", port=80)`. The HTTP server
can start before DHCP completes and is accessible once an address is assigned.
Find that address in your DHCP server's lease list, then open `http://BOARD_IP/`.
To stop the app and return to the REPL, interrupt it with Ctrl-C.

### Dependencies

`package.json` pins the verified driver and Microdot revisions for reproducible
installation:

- [PCF8575](https://github.com/mcauser/micropython-pcf8575)
- [XL9535 / XL9555](https://github.com/mattytrentini/micropython-xl9535)
- [ADS1x15](https://github.com/robert-hh/ads1x15)
- [DS3231](https://github.com/mattytrentini/micropython-DS3231-AT24C32)
- [ST7789 and CO16 display configuration](https://github.com/mattytrentini/st7789py_mpy)
- [Microdot](https://github.com/miguelgrinberg/microdot), installed as its standalone
  base module; no framework extensions are required.

The DS3231 is read without setting its time on startup. ADC and display drivers
are installed but are not initialized by this app.
Update dependency pins deliberately when adopting a new driver revision.

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

## Layout

- `main.py`: MicroPython boot entry point and async server startup.
- `co16.py`: network setup, relay control/readback, input snapshots and DS3231 clock.
- `co16_web.py`: async routes and API error responses.
- `co16_static/`: HTML, CSS and JavaScript dashboard.
- `package.json`: application assets and pinned mip dependencies.

MIT license; copyright 2026 Matt Trentini. Dependency licenses remain with their
respective upstream projects.
