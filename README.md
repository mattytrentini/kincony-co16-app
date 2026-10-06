# KinCony CO16 application

MicroPython application for the [KinCony CO16](https://www.kincony.com/esp32-s3-16-channel-analog-input-smart-controller.html), using [Microdot](https://github.com/miguelgrinberg/microdot) for an asynchronous HTTP server.

The application serves a read-only browser dashboard and a versioned JSON REST
API. It reads the 16 relay control levels and 16 digital inputs; it does not
switch relays, change input configuration, set the RTC, or initialize the LCD,
ADCs or optional modules. Ethernet uses the built-in W5500 driver on SPI1,
leaving shared SPI2 peripherals untouched.

## Requirements

- Assumes the appropriate [KINCONY_CO16 MicroPython firmware](https://github.com/mattytrentini/micropython/tree/kincony-co16/ports/esp32/boards/KINCONY_CO16)
  is already installed.
- An Ethernet connection to a LAN with DHCP. HTTP listens on port **80**;
  no WiFi credentials or secrets are stored in this repository.

This is an **unauthenticated, unencrypted, trusted-LAN interface**. Do not expose
it directly to the Internet. There are no output-writing API routes.

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

RTC, ADC and display drivers are installed but are not initialized by this app.
Update dependency pins deliberately when adopting a new driver revision.

## HTTP interface

`GET /` serves the dashboard. It shows the board and firmware, Ethernet state,
IP address, available heap, and numbered channel states. It refreshes every five
seconds and also has a manual **Refresh** button. Failed reads are reported and
last-known channel states are explicitly marked stale rather than presented as
current data. The page has no external assets or framework dependencies.

Only the fixed `/assets/app.css` and `/assets/app.js` resources are served;
there is no arbitrary filesystem-serving route.

## REST API

All API responses are JSON with `Cache-Control: no-store`. The following
resources support `GET` and `HEAD`; unsupported methods return `405` with
`Allow: GET, HEAD`. Unknown API routes return `404`.

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

API errors use the same `error.code` / `error.message` structure. Unexpected
errors are logged on the serial console and return a generic `500`, without
exposing exception text in HTTP responses.

```sh
curl http://BOARD_IP/api/v1/status
curl http://BOARD_IP/api/v1/io
```

## Verification

The installed application was exercised on the CO16 with real TCP loopback
HTTP requests: status and IO snapshots, all static assets, HEAD, read-only
method rejection, missing routes, filesystem-path rejection, and a `503`
caused by an actual failed I2C read. Relay readback remained `0xffff`; no
relay-control writes were made.

Desktop and 390-pixel-wide browser views were checked through a temporary USB
forwarder to that same board HTTP server. Manual refresh, stale-data reporting
on a failed request, and recovery were exercised. The forwarder was removed
after verification; it is not an application dependency.

Default-target mip installation was checked with `/main.py` absent: it created
the root boot entry point and installed all dependencies without a separate
file copy.

The root `main.py` was then started by a normal MicroPython soft reboot and
its startup messages observed without an exception. Ethernet reported
disconnected with no IP, so external LAN access still requires a DHCP connection.

## Layout

- `main.py`: MicroPython boot entry point and async server startup.
- `co16.py`: board network setup and read-only hardware snapshots.
- `co16_web.py`: async routes and API error responses.
- `co16_static/`: HTML, CSS and JavaScript dashboard.
- `package.json`: application assets and pinned mip dependencies.

MIT license; copyright 2026 Matt Trentini. Dependency licenses remain with their
respective upstream projects.
