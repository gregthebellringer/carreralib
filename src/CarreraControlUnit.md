# Carrera Control Unit API Reference

A summary of the carreralib API for interfacing with Carrera DIGITAL 124/132 slotcar systems.

## Library Features

| Feature | Description |
|---------|-------------|
| Control Unit Interface | Query version/status, start races, reset timers, control cars |
| Car Management | Set speed, brake, and fuel values for individual cars |
| Race Monitoring | Poll for timer events, lap times, fuel levels, pit lane status |
| Display Control | Manage lap counters and position tower displays |
| Dual Connectivity | Serial (USB) or Bluetooth LE (via Carrera AppConnect) |
| Demo RMS | Built-in curses-based Race Management System |

## Key Files

| File | Description |
|------|-------------|
| cu.py | Main ControlUnit class with the API |
| connection.py | Abstract connection interface |
| serial.py | Serial/USB connection |
| ble.py | Bluetooth LE connection |
| protocol.py | Binary protocol encoder/decoder |
| \_\_main\_\_.py | Demo Race Management System |

## Connecting to the Control Unit

### Serial/USB Connection

```python
from carreralib import ControlUnit

# Linux
cu = ControlUnit('/dev/ttyUSB0')

# Windows
cu = ControlUnit('COM3')

# macOS
cu = ControlUnit('/dev/cu.usbserial-XXXX')
```

### Bluetooth LE Connection (via Carrera AppConnect)

```python
cu = ControlUnit('C6:34:FA:1D:1D:5D')  # MAC address
```

The library auto-detects the connection type based on the device string format.

### Connection Parameters

| Connection | Default Settings |
|------------|------------------|
| Serial | 19200 baud, 8N1 |
| BLE | 1.0 second timeout |

### Connection with Custom Timeout

```python
# BLE with custom timeout
cu = ControlUnit('C6:34:FA:1D:1D:5D', timeout=2.0)
```

### Discovering Available Devices

```bash
# List available serial ports and Bluetooth devices
python -m carreralib
```

## Controller Addresses

| Address | Controller |
|---------|------------|
| 0 | Controller #1 |
| 1 | Controller #2 |
| 2 | Controller #3 |
| 3 | Controller #4 |
| 4 | Controller #5 |
| 5 | Controller #6 |
| 6 | Autonomous Car |
| 7 | Pace Car |

### Controller Address Examples

```python
cu.setspeed(0, 15)   # Set Controller #1 speed to max
cu.setspeed(1, 10)   # Set Controller #2 speed to 10
cu.setfuel(6, 14)    # Set autonomous car fuel
cu.setpos(7, 8)      # Set pace car position on display
```

## Value Ranges

| Parameter | Range | Description |
|-----------|-------|-------------|
| Speed | 0-15 | 0 = stop, 15 = maximum |
| Brake | 0-15 | 0 = none, 15 = maximum |
| Fuel | 0-15 | 0 = empty, 15 = full |

### Speed Values

| Value | Meaning |
|-------|---------|
| 0 | Minimum/Stop |
| 1-7 | Low speed |
| 8 | Medium speed |
| 9-14 | High speed |
| 15 | Maximum speed |

### Fuel Values

| Value | Meaning |
|-------|---------|
| 0 | Empty |
| 1-7 | Low fuel |
| 8 | Half fuel |
| 9-14 | High fuel |
| 15 | Full |

### Brake Values

| Value | Meaning |
|-------|---------|
| 0 | No braking |
| 1-7 | Light braking |
| 8 | Medium braking |
| 9-14 | Heavy braking |
| 15 | Maximum braking |

### Setting Car Parameter Examples

```python
# Speed examples
cu.setspeed(0, 15)   # Set car 0 (Controller #1) to max speed
cu.setspeed(1, 8)    # Set car 1 (Controller #2) to half speed
cu.setspeed(7, 3)    # Set pace car to slow speed

# Fuel examples
cu.setfuel(0, 15)    # Set car 0 to full fuel
cu.setfuel(0, 8)     # Set car 0 to half fuel

# Check current fuel levels for all 8 cars
status = cu.poll()
if isinstance(status, ControlUnit.Status):
    print(status.fuel)  # e.g., (15, 12, 0, 0, 0, 0, 14, 15)
```

## Polling the Control Unit

```python
event = cu.poll()
```

Returns one of two types:

### ControlUnit.Status

Returned when no timer events are pending.

| Attribute | Description |
|-----------|-------------|
| `fuel` | 8-item tuple of fuel levels (0-15) |
| `start` | Start light indicator (0-9) |
| `mode` | 4-bit mode bitmask |
| `pit` | 8-item tuple of pit lane status (True/False) |
| `display` | Number of drivers to display (6 or 8) |

### ControlUnit.Timer

Returned when a car crosses a sensor.

| Attribute | Description |
|-----------|-------------|
| `address` | Controller address (0-7) |
| `timestamp` | Time in milliseconds (32-bit) |
| `sector` | Sector number (1=finish, 2-3=check lanes) |

### Polling Example

```python
from carreralib import ControlUnit

cu = ControlUnit('/dev/ttyUSB0')

while True:
    event = cu.poll()

    if isinstance(event, ControlUnit.Timer):
        # A car crossed a sensor
        print(f"Car {event.address} at {event.timestamp}ms, sector {event.sector}")

    elif isinstance(event, ControlUnit.Status):
        # General status update
        print(f"Fuel levels: {event.fuel}")
        print(f"Pit status: {event.pit}")

        # Check mode flags
        if event.mode & ControlUnit.Status.FUEL_MODE:
            print("Fuel mode enabled")
```

## Start Light Indicator Values

| Value | Meaning |
|-------|---------|
| 0 | All lights off |
| 1 | Light 1 on |
| 2 | Lights 1-2 on |
| 3 | Lights 1-3 on |
| 4 | Lights 1-4 on |
| 5 | Lights 1-5 on |
| 6 | All 5 red lights on (ready) |
| 7 | Green light (GO!) |
| 8 | Race in progress |
| 9 | Race in progress / lights off |

### Start Light Example

```python
from carreralib import ControlUnit

cu = ControlUnit('/dev/ttyUSB0')

while True:
    status = cu.poll()

    if isinstance(status, ControlUnit.Status):
        start = status.start

        if start == 0:
            print("Lights off - waiting")
        elif 1 <= start <= 5:
            print(f"Countdown: {start} light(s) on")
        elif start == 6:
            print("All red lights on - GET READY!")
        elif start == 7:
            print("GREEN LIGHT - GO!")
        elif start >= 8:
            print("Race in progress")
```

## Mode Bitmask Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `FUEL_MODE` | 0x1 | Fuel mode enabled |
| `REAL_MODE` | 0x2 | Real fuel mode enabled |
| `PIT_LANE_MODE` | 0x4 | Pit lane adapter connected |
| `LAP_COUNTER_MODE` | 0x8 | Lap counter connected |

## Control Unit Buttons

| Constant | ID | Function |
|----------|-----|----------|
| `PACE_CAR_ESC_BUTTON_ID` | 1 | Pace Car / ESC |
| `START_ENTER_BUTTON_ID` | 2 | Start / Pause |
| `SPEED_BUTTON_ID` | 5 | Speed setting |
| `BRAKE_BUTTON_ID` | 6 | Brake setting |
| `FUEL_BUTTON_ID` | 7 | Fuel setting |
| `CODE_BUTTON_ID` | 8 | Code setting |

## Common Operations

### Starting a Race

```python
cu.start()  # Initiates start sequence
```

### Pausing a Race

```python
cu.start()  # Same button toggles pause
# or
cu.press(ControlUnit.START_ENTER_BUTTON_ID)
```

### Setting Car Parameters

```python
cu.setspeed(0, 15)   # Set car 0 to max speed
cu.setbrake(0, 8)    # Set car 0 brake to medium
cu.setfuel(0, 15)    # Set car 0 to full fuel
```

### Pace Car Control

```python
from carreralib import ControlUnit

cu = ControlUnit('/dev/ttyUSB0')

# Configure pace car speed before deploying
cu.setspeed(7, 6)  # Set to slow speed

# Deploy the pace car
cu.press(ControlUnit.PACE_CAR_ESC_BUTTON_ID)

# To recall/stop the pace car, press the button again
cu.press(ControlUnit.PACE_CAR_ESC_BUTTON_ID)

# Other pace car settings
cu.setfuel(7, 15)  # Full fuel
cu.setbrake(7, 4)  # Light braking
```

### Position Tower

```python
cu.setpos(0, 1)   # Set car 0 to position 1
cu.setlap(10)     # Set lap counter to 10
cu.clrpos()       # Clear/reset position tower
```

### Reset Timer

```python
cu.reset()
```

### Get Firmware Version

```python
version = cu.version()  # Returns e.g., '5337'
```

### Close Connection

```python
cu.close()
```

## Example: Race Monitor

```python
from carreralib import ControlUnit

cu = ControlUnit('/dev/ttyUSB0')

print(f"Connected to CU version: {cu.version()}")

cu.start()  # Begin race

while True:
    event = cu.poll()

    if isinstance(event, ControlUnit.Timer):
        print(f"Car {event.address} crossed sector {event.sector} at {event.timestamp}ms")

    elif isinstance(event, ControlUnit.Status):
        if event.mode & ControlUnit.Status.FUEL_MODE:
            print(f"Fuel levels: {event.fuel}")
```
