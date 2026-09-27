# Tamagonion ESP8266 Display

A small wireless 240x240 display client for [Tamagonion](https://github.com/daxAKAhackerman/tamagonion).

This project turns an inexpensive ESP8266 weather clock into a dedicated Tamagonion screen. Tamagonion keeps all Tor-state logic and rendering decisions; the ESP8266 simply authenticates the client and displays the rendered 48x20 UTF-8 viewport.

## What this gives you

- The real Tamagonion Home, Status, and Hints views
- Stinky animations and room objects
- Tor relay states such as Exit, Guard, HSDir, V2Dir, BadExit, bootstrap, and warning states
- Wi-Fi transport over a persistent TCP connection
- HMAC-SHA256 challenge-response authentication
- A pairing screen with IP address, port, and a short pairing code
- ESPHome OTA updates after the first flash
- A simulator that uses the real Tamagonion renderer, so the display can be tested without a live Tor relay

## Relationship to Tamagonion

This is an independent companion project for [daxAKAhackerman/tamagonion](https://github.com/daxAKAhackerman/tamagonion).

Tamagonion remains the source of truth for:

- Tor relay state
- Stinky's behavior
- room objects
- screen selection
- terminal rendering

This repository only provides the external ESP8266 display client and test tooling.

The display protocol intentionally does not contain concepts such as `HOME`, `STATUS`, or `HINTS`. Tamagonion sends complete rendered frames, so new upstream views can work without changing the ESP8266 firmware.

See [docs/protocol.md](docs/protocol.md) for the wire protocol.

## Development disclosure

The upstream Tamagonion repository explicitly states that it contains no AI-generated code.

This companion display repository was developed with substantial assistance from OpenAI ChatGPT. Hardware identification, flashing, integration decisions, physical-device testing, performance measurements, and final project ownership remain with this repository's maintainer.

This disclosure applies to this repository only and does not describe the development process of upstream Tamagonion.

---

# Hardware

## Tested hardware

The firmware was developed and tested on a small **SD PRO-style Smart Weather Clock** with:

- ESP-12F / ESP8266
- 4 MB flash
- 1.54-inch 240x240 IPS LCD
- ST7789 display controller
- USB power
- stock browser-based OTA firmware update

### Tested pinout

| Function | ESP8266 GPIO |
|---|---:|
| SPI MOSI | GPIO13 |
| SPI Clock | GPIO14 |
| Display DC | GPIO0 |
| Display Reset | GPIO2 |
| Backlight | GPIO5 |

The tested board does not require a separately configured display chip-select pin.

## Likely compatible hardware

Good candidates include ESP8266 versions of:

- GeekMagic SmallTV
- GeekMagic SmallTV Ultra

Community firmware projects for these models report the same general combination of ESP8266/ESP-12F, ST7789 240x240 LCD, and very similar display pin mapping.

The first-flash method may differ between stock firmware versions even when the hardware is compatible.

## Do not use this build on ESP32 variants

Do not flash this ESP8266 firmware onto visually similar devices using:

- ESP32-C2 / ESP8684
- ESP32-WROOM
- other ESP32 variants

Some GeekMagic SmallTV generations and NM-TV-154-style devices look nearly identical from the outside but use different processors.

If you are unsure, verify that the module is marked **ESP-12F** or **ESP8266MOD** before flashing.

---

# Quick installation

You need:

- the compatible display
- a 2.4 GHz Wi-Fi network
- Python 3
- a Windows, Linux, or macOS computer
- basic command-line familiarity

No ESP8266 programming experience is required for the normal SD PRO installation.

## 1. Clone the repository

```bash
git clone https://github.com/THEWHIFF/tamagonion-esp8266-display.git
cd tamagonion-esp8266-display
```

## 2. Create a Python environment

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The firmware is currently validated with **ESPHome 2026.9.0**.

## 3. Create `secrets.yaml`

Linux / macOS:

```bash
cp secrets.example.yaml secrets.yaml
```

Windows PowerShell:

```powershell
Copy-Item secrets.example.yaml secrets.yaml
```

Open `secrets.yaml` and replace all example values.

The file is ignored by Git and should never be committed.

### Generate a pairing code

A 10-character code is easy to type while still providing a large local pairing key space.

```bash
python -c "import secrets; a='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; print(''.join(secrets.choice(a) for _ in range(10)))"
```

Example output:

```text
7KW3M9DT2F
```

Put your generated value in `secrets.yaml`:

```yaml
tamagonion_pairing_code: "7KW3M9DT2F"
```

Do not copy the example code for a real installation.

## 4. Validate and compile

```bash
esphome config tamagonion-display.yaml
esphome compile tamagonion-display.yaml
```

A successful build ends with:

```text
Successfully compiled program.
```

---

# First flash from the stock SD PRO firmware

This is the method used on the tested hardware. It does not require opening the case or soldering.

## 1. Find the clock's current IP address

Find the weather clock in your router's connected-device list and open its address in a browser.

Example:

```text
http://192.168.1.50
```

## 2. Open the stock firmware updater

On the tested unit, the stock interface contains:

```text
Firmware Update (OTA)
```

The original updater checks that the uploaded filename begins with:

```text
SDP
```

## 3. Locate the compiled ESPHome firmware

On Linux or macOS:

```bash
find .esphome/build -path '*/.pioenvs/*/firmware.bin' -print
```

Copy the resulting file to a convenient filename accepted by the stock updater:

```bash
cp "$(find .esphome/build -path '*/.pioenvs/*/firmware.bin' | head -1)" \
  SDP_TAMAGONION.bin
```

On Windows, locate `firmware.bin` below:

```text
.esphome\build\
```

and make a copy named:

```text
SDP_TAMAGONION.bin
```

## 4. Upload the firmware

In the stock **Firmware Update (OTA)** page, select:

```text
SDP_TAMAGONION.bin
```

Start the update and **do not remove power while flashing**.

The display will reboot into the Tamagonion firmware.

---

# First Wi-Fi setup

The custom firmware does not need your Wi-Fi password stored in the public YAML file.

If no saved network is available, the display creates a temporary setup access point named:

```text
Tamagonion Display Setup
```

Connect to it using the fallback AP password from `secrets.yaml`.

A captive portal should open automatically. If it does not, browse to:

```text
http://192.168.4.1
```

Select your 2.4 GHz network and enter its password.

The credentials are stored locally on the ESP8266.

---

# Pairing screen

When Tamagonion is not connected, the display shows:

- its IP address
- TCP port
- pairing code
- connection state

The default TCP port is:

```text
18511
```

When an authenticated client disconnects, the Tamagonion frame is cleared and the display returns to this screen.

---

# Updating the display later

After the first custom flash, use native ESPHome OTA instead of the original SD PRO updater.

```bash
source .venv/bin/activate
esphome run tamagonion-display.yaml --device DISPLAY_IP
```

Example:

```bash
esphome run tamagonion-display.yaml --device 192.168.1.50
```

The firmware is compiled, uploaded over Wi-Fi, and rebooted automatically.

---

# Test the display without a Tor relay

The included simulator uses the **real Tamagonion renderer** and injects simulated Tor states.

Tamagonion 1.4.1 currently requires Python 3.14, so using a separate simulator environment is recommended.

## Create the simulator environment

```bash
python3.14 -m venv tools/.sim-venv
tools/.sim-venv/bin/pip install -r tools/requirements-simulator.txt
```

The simulator reads the pairing code from the repository's `secrets.yaml` by default.

## List available states

```bash
tools/.sim-venv/bin/python tools/tamagonion_simulator.py --list
```

## Run the complete demo

```bash
tools/.sim-venv/bin/python tools/tamagonion_simulator.py \
  --host 192.168.1.50
```

The automatic demo cycles through states including:

- healthy relay
- Exit
- Guard
- HSDir
- V2Dir
- BadExit
- bootstrap
- network failure
- missing relay flags
- unreachable ORPort
- obsolete Tor version
- sleeping Stinky
- Status
- Hints

## Test one state

```bash
tools/.sim-venv/bin/python tools/tamagonion_simulator.py \
  --host 192.168.1.50 \
  --state badexit
```

Status view:

```bash
tools/.sim-venv/bin/python tools/tamagonion_simulator.py \
  --host 192.168.1.50 \
  --state all_objects \
  --screen status
```

---

# How it works

```text
Tamagonion
    |
    | renders its normal 48x20 viewport
    v
Authenticated TCP connection
    |
    | complete UTF-8 frame
    v
ESP8266
    |
    | event-driven LCD refresh
    v
240x240 ST7789 display
```

The ESP8266 has no Tor-specific state machine and does not recreate Tamagonion's UI.

That separation is deliberate: application behavior stays upstream in Tamagonion, while this project remains a small display transport.

---

# Authentication and security

Every TCP connection starts with a fresh random challenge.

The client replies with an HMAC-SHA256 digest derived from the shared pairing code. The pairing code itself is not transmitted during normal authentication.

A captured authentication response cannot simply be replayed on a later connection because the challenge changes.

Display frames are authenticated but **not encrypted**. A device that can passively observe traffic on the same network may be able to read the screen contents.

Use this project on a trusted local network and do not expose TCP port `18511` directly to the Internet.

The exact protocol is documented in [docs/protocol.md](docs/protocol.md).

---

# Performance

The ESP8266 uses an 8-bit, 25% display buffer to stay within its RAM budget.

On the tested hardware, a complete 240x240 refresh takes about **130 ms**.

ESPHome redraws a 25% fractional display buffer in four passes. The rendering lambda therefore has no side effects and the TCP component triggers a display update only after receiving a complete frame.

Tamagonion's normal rendering cadence is much slower than video, so this is sufficient for Stinky and room-state updates.

---

# Recovery

Custom firmware installation always carries some risk.

Before flashing an unknown hardware revision:

1. verify that the processor is ESP8266 / ESP-12F
2. verify the display controller and pin mapping
3. keep the display powered throughout OTA flashing
4. never flash this ESP8266 binary onto an ESP32-based unit

If OTA recovery is lost, the ESP8266 can normally be recovered using its UART programming interface and a 3.3 V USB-to-serial adapter. That requires opening the device and is outside the normal SD PRO installation procedure.

Never connect 5 V directly to ESP8266 3.3 V programming pins.

---

# Tested on real hardware

The following have been validated on the physical display:

- first flash through the stock SD PRO OTA page
- ESPHome OTA updates
- ESP-12F / ESP8266
- 240x240 ST7789 display
- 8-bit / 25% display buffer
- 48x20 Unicode viewport
- box-drawing and block characters
- event-driven LCD refresh
- persistent TCP connection
- reconnect handling
- HMAC-SHA256 authentication
- short pairing code
- real Tamagonion renderer output
- Stinky animations
- room objects
- multiple simulated Tor states
- Status view
- Hints view

---

# Useful hardware references

Community projects for similar displays include:

- [iodn/geekmagic-tv-esp8266](https://github.com/iodn/geekmagic-tv-esp8266)
- [Times-Z/GeekMagic-Open-Firmware](https://github.com/Times-Z/GeekMagic-Open-Firmware)
- [giovi321/smalltv-mod](https://github.com/giovi321/smalltv-mod)

These are particularly useful when identifying hardware revisions that use the same case but a different processor.

---

# Upstream project

Tamagonion:

- Repository: [github.com/daxAKAhackerman/tamagonion](https://github.com/daxAKAhackerman/tamagonion)
- Author: [@daxAKAhackerman](https://github.com/daxAKAhackerman)

This repository is not a fork of Tamagonion. It is a companion display project built around Tamagonion's rendered viewport.
