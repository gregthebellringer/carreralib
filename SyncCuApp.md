# Control Unit and Web App Synchronization

This document describes how the Web App synchronizes with the Carrera Control Unit (real hardware or mock), highlighting what behaves identically and what differs between the two.

## Architecture Overview

```
┌─────────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  Web Browser (JS)   │────▶│   Python Server     │────▶│  Control Unit    │
│  app.js             │ WS  │   app.py            │     │  (Real or Mock)  │
└─────────────────────┘     └─────────────────────┘     └──────────────────┘
```

- **Web Browser**: Displays UI, receives status via WebSocket every 100ms
- **Python Server (RaceManager)**: Bridges web clients to Control Unit, maintains state
- **Control Unit**: Real hardware or MockConnection (mock.py)

---

## State Synchronization

### Data Flow

| Source | Direction | Destination | Data |
|--------|-----------|-------------|------|
| Control Unit | → | Server | Status (poll), Timer events |
| Server | → | Browser | WebSocket JSON status (100ms interval) |
| Browser | → | Server | API calls (connect, start, pause, stop, pace car) |
| Server | → | Control Unit | Commands (start, press, setword) |

### Synchronized State Variables

| State | Server (Python) | Client (JavaScript) | Source of Truth |
|-------|-----------------|---------------------|-----------------|
| `connected` | `race_manager.connected` | `this.connected` | Server |
| `start_light` | `last_start_light` | `currentStartLightState` | Control Unit |
| `race_has_started` | `race_has_started` | `raceHasStarted` | Server (derived) |
| `pace_car_deployed` | `pace_car_deployed` | `paceCarDeployed` | Server |
| `cars` (standings) | `race_manager.cars` | Updated from WebSocket | Server |
| `fuel[0-7]` | From Status.fuel | Displayed in UI | Control Unit |
| `pit[0-7]` | From Status.pit | Displayed in UI | Control Unit |

---

## Start Light States

### Identical Behavior (Real CU = Mock = App)

| State | Value | Real CU | Mock | App Display |
|-------|-------|---------|------|-------------|
| OFF | 0 | All lights off | All lights off | Empty or blinking red (if paused) |
| RED_1 | 1 | Light 1 on | Light 1 on | 1 red light, "Countdown: 5" |
| RED_2 | 2 | Lights 1-2 on | Lights 1-2 on | 2 red lights, "Countdown: 4" |
| RED_3 | 3 | Lights 1-3 on | Lights 1-3 on | 3 red lights, "Countdown: 3" |
| RED_4 | 4 | Lights 1-4 on | Lights 1-4 on | 4 red lights, "Countdown: 2" |
| RED_5 | 5 | Lights 1-5 on | Lights 1-5 on | 5 red lights, "Countdown: 1" |
| RED_ALL | 6 | All 5 red | All 5 red | All red, "GET READY!" |
| GREEN | 7 | Green light | Green light | All green, "GO! GO! GO!" |
| RACE | 8/9 | Lights off | Lights off | Slow blinking green, "Race in progress" |

### Key Difference: App Visual Enhancement

The app shows **slow blinking green lights** during the race (state >= 8), whereas the real Control Unit and mock both have lights off. This is a visual enhancement for the web interface only.

---

## Race Control Commands

### Start Race

| Step | Real CU | Mock | App Behavior |
|------|---------|------|--------------|
| 1. Press START | `cu.start()` | `cu.start()` | Calls `/api/race/start` |
| 2. Fresh start | Countdown sequence (1s per light) | Same timing | Same timing |
| 3. Resume (paused) | Instant resume (no countdown) | Instant resume | Instant resume |

**Identical**: Both real CU and mock use the same START button to begin countdown or resume.

### Pause Race

| Action | Real CU | Mock | App |
|--------|---------|------|-----|
| During race | Press START → state=0 | Press START → state=0, is_paused=True | Shows "Race is paused", blinking red |
| ESC during countdown | Cancels countdown | Cancels countdown, is_paused=False | Returns to Start Race button |

**Identical**: Toggling pause works the same way.

### Stop Race

| Action | Real CU | Mock | App |
|--------|---------|------|-----|
| Stop command | Press START (pause) + reset | Pause + reset is_paused=False + reset data | Calls pause, resets state, shows Start button |

**App-specific**: The "Stop Race" button is an app concept that combines pause + reset. The real CU doesn't have a dedicated "stop" - you would pause and manually reset.

---

## Pace Car

### Identical Behavior

| Action | Real CU | Mock | App |
|--------|---------|------|-----|
| Deploy | Press PACE_CAR button | Same button press | Calls `/api/pacecar/deploy` |
| Recall | Press PACE_CAR button again | Same button press | Calls `/api/pacecar/recall` |
| Display | Yellow caution lights | Yellow blink (UI) | Blinking yellow lights |

**Difference**: App tracks `pace_car_deployed` state separately. Real CU doesn't expose this directly in status.

---

## Timer Events

### Identical Behavior

| Aspect | Real CU | Mock |
|--------|---------|------|
| Format | `Timer(address, timestamp, sector)` | Same format |
| Sector 1 | Finish line crossing | Finish line crossing |
| Sectors 2-3 | Check lanes | (Not implemented in mock) |
| Timestamp | 32-bit ms since race start | Same |

### App Processing

The server processes timer events identically for both:
1. Receives `Timer` from `cu.poll()`
2. Updates lap count, calculates lap time
3. Updates best lap time if applicable
4. Sends to browser via WebSocket

---

## Fuel and Pit Lane

### Identical Behavior

| Aspect | Real CU | Mock |
|--------|---------|------|
| Fuel range | 0-15 | 0-15 |
| Fuel consumption | Per lap when FUEL_MODE | Per lap when FUEL_MODE |
| Pit status | True/False per car | True/False per car |

### App Display

| Fuel Level | Visual |
|------------|--------|
| > 40% | Green bar |
| 20-40% | Yellow bar (low class) |
| < 20% | Red blinking bar (critical class) |
| In pit | "PIT" badge shown |

---

## What's Identical (Real CU = Mock = App)

1. **Start light countdown sequence** - Same timing (1s per light)
2. **START button behavior** - Toggles start/pause
3. **ESC button** - Cancels countdown, toggles pace car
4. **Timer event format** - Same address, timestamp, sector structure
5. **Fuel values** - 0-15 scale
6. **Pause/resume** - Instant resume without countdown
7. **Status polling** - Returns Status or Timer based on pending events

---

## What Differs (App enhancements/limitations)

### App Enhancements

| Feature | Real CU/Mock | App |
|---------|--------------|-----|
| Race in progress display | Lights off (state 8/9) | Slow blinking green |
| Paused display | Lights off (state 0) | Blinking red + "Race is paused" |
| Stop Race | Manual pause + reset | One-button stop + data reset |
| Pace car state | Not in status | Tracked separately |

### App Limitations

| Feature | Real CU | Mock | App |
|---------|---------|------|-----|
| Check lanes (sectors 2-3) | Supported | Not implemented | Not displayed |
| Speed/Brake/Fuel settings | Full control | Full control | Not implemented in UI |
| Position tower | Full control | Full control | Not implemented in UI |
| 8-driver display toggle | Supported | Supported | Fixed at 6 cars |

---

## WebSocket Message Format

```json
{
  "type": "status",
  "connected": true,
  "start_light": 9,
  "mode": 0,
  "pace_car_deployed": false,
  "race_has_started": true,
  "cars": [
    {
      "address": 0,
      "position": 1,
      "laps": 5,
      "last_lap_time": 5234,
      "best_lap_time": 4890,
      "fuel": 12,
      "in_pit": false,
      "last_timestamp": 26170
    }
  ]
}
```

---

## Key Synchronization Rules

1. **State before UI**: Client sets state variables before updating UI to prevent flickering
2. **Server is source of truth**: `race_has_started` is derived from server state (mock's `is_paused` or `start_light > 0`)
3. **100ms polling**: WebSocket pushes status every 100ms for responsive UI
4. **Stateless API calls**: Each API call (start, pause, stop) is fire-and-forget; state comes back via WebSocket
