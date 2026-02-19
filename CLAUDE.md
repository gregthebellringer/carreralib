# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python interface to Carrera DIGITAL 124/132 slotcar systems. Supports serial (USB) and Bluetooth LE (via Carrera AppConnect) connections. Includes a curses-based demo RMS, a FastAPI web app for race management, a TCP server for testing, and a mock control unit for development without hardware.

## Common Commands

```bash
# Install from source (editable/dev mode)
pip install -e .

# Run tests with coverage
pytest --cov=carreralib

# Run all tox environments (tests, linting, docs, manifest check)
tox

# Run only linting
tox -e flake8

# Run only tests
tox -e py

# Build documentation
tox -e docs

# Run the curses-based demo RMS
python -m carreralib /dev/ttyUSB0

# Run the web app (auto-connects to mock if no server available)
python -m carreralib.webapp
python -m carreralib.webapp --port 8000 --device socket://localhost:5000

# Run the test TCP server (simulates a Control Unit)
python -m carreralib.server --port 5000 --simulate
```

## Code Style

- Formatter: **Black** (enforced via flake8-black)
- Max line length: 80 (but E501 is ignored per Black convention)
- Linting: flake8 with bugbear and import-order plugins
- Python: >= 3.7

## Architecture

### Core Library (`src/carreralib/`)

The library communicates with the Carrera Control Unit via a custom binary protocol (not ASCII/JSON).

- **`cu.py`** — `ControlUnit` class: main API surface. Wraps a `Connection` and provides methods like `poll()`, `start()`, `setspeed()`, `setbrake()`, `setfuel()`, `setpos()`, `setlap()`, `reset()`, `version()`. Returns `ControlUnit.Status` or `ControlUnit.Timer` named tuples from `poll()`.
- **`protocol.py`** — Binary protocol encoder/decoder with custom format strings and checksum calculation.
- **`connection.py`** — Abstract `Connection` base class with `open(device)` factory that auto-detects Serial vs BLE based on device string format.
- **`serial.py`** — Serial/USB connection (pyserial, 19200 baud, 8N1). Uses `"` and `$` as frame delimiters.
- **`ble.py`** — Bluetooth LE connection (bleak). Runs asyncio in a separate thread with queue-based I/O.
- **`mock.py`** — Full mock control unit with `MockConnection`, `RaceSimulator` (generates realistic lap times/fuel consumption), and `StartLightSequence` (threaded countdown with 1s intervals).

### Web App (`src/carreralib/webapp/`)

Single-page web app using FastAPI + vanilla JS.

- **`app.py`** — `RaceManager` class bridges web clients to `ControlUnit`. WebSocket endpoint (`/ws/race`) pushes status every 100ms. REST endpoints for connect, disconnect, race control (start/pause/stop), pace car, and settings.
- **`templates/index.html`** — Single HTML page with start lights visualization, race controls, standings, session settings, and connection panel.
- **`static/js/app.js`** — `RaceApp` class manages client-side state and WebSocket connection.
- **`static/css/style.css`** — Dark theme, mobile-first responsive design.

### Other Entry Points

- **`__main__.py`** — Curses-based demo RMS with keyboard controls (SPACE=start/pause, ESC=pace car, R=reset, Q=quit).
- **`server.py`** — TCP server that simulates a Control Unit on a socket (compatible with pyserial's `socket://` URL scheme).
- **`fw.py`** — Firmware update utility.

### Key Design Patterns

- **Factory pattern**: `connection.open(device)` auto-detects connection type from device string
- **Named tuples**: `Status` and `Timer` for immutable poll responses
- **State machine**: `StartLightSequence` manages countdown states (0=OFF through 9=RACE)
- **Source of truth**: In the web app, the server (`RaceManager`) is authoritative; the browser receives state via WebSocket and sends commands via REST API

## Reference Documentation

- **`src/CarreraControlUnit.md`** — Detailed CU API reference: controller addresses (0-7), value ranges (speed/brake/fuel 0-15), start light states (0-9), mode bitmasks, button IDs, and code examples.
- **`SyncCuApp.md`** — How the web app synchronizes with the Control Unit: data flow, state variables, differences between real CU and app behavior.
