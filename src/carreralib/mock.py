"""Mock Control Unit for testing without physical hardware."""

import queue
import random
import threading
import time
from collections import namedtuple

from . import protocol
from .connection import Connection, TimeoutError


TimerEvent = namedtuple("TimerEvent", "address timestamp sector")


class StartLight:
    """Start light state constants."""
    OFF = 0           # All lights off (idle/waiting)
    RED_1 = 1         # First red light on
    RED_2 = 2         # Lights 1-2 on
    RED_3 = 3         # Lights 1-3 on
    RED_4 = 4         # Lights 1-4 on
    RED_5 = 5         # Lights 1-5 on
    RED_ALL = 6       # All 5 red lights on (GET READY!)
    GREEN = 7         # Green light (GO!)
    RACE = 9          # Race in progress / lights off


class StartLightSequence:
    """Manages the start light countdown sequence.

    The sequence progresses through these states:
    - 0: All lights off (idle)
    - 1-5: Red lights counting up (one per interval)
    - 6: All red lights on (GET READY!)
    - 7: Green light (GO!) - race timer starts here
    - 9: Race in progress (lights off)
    """

    def __init__(self, state, red_interval=1.0, green_duration=0.5):
        """Initialize start light sequence.

        Args:
            state: ControlUnitState to update.
            red_interval: Time between red light steps in seconds.
            green_duration: How long green light stays on before race starts.
        """
        self.state = state
        self.red_interval = red_interval
        self.green_duration = green_duration
        self._running = False
        self._thread = None
        self._on_race_start = None  # Callback when race starts

    def start(self, on_race_start=None):
        """Start the countdown sequence.

        Args:
            on_race_start: Optional callback called when green light triggers.
        """
        if self._running:
            return  # Already running

        self._on_race_start = on_race_start
        self._running = True
        self.state.start = StartLight.OFF
        self._thread = threading.Thread(target=self._run_sequence, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the countdown sequence."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def is_running(self):
        """Check if sequence is currently running."""
        return self._running

    def _run_sequence(self):
        """Run the countdown sequence."""
        # Brief pause at OFF before starting countdown
        time.sleep(self.red_interval)

        # Count up red lights: 1 -> 2 -> 3 -> 4 -> 5 -> 6
        for light in range(StartLight.RED_1, StartLight.RED_ALL + 1):
            if not self._running:
                return
            self.state.start = light
            time.sleep(self.red_interval)

        if not self._running:
            return

        # Green light - GO!
        self.state.start = StartLight.GREEN
        self.state.reset_timer()  # Timer starts at green light

        # Call the race start callback
        if self._on_race_start:
            self._on_race_start()

        time.sleep(self.green_duration)

        if not self._running:
            return

        # Race in progress
        self.state.start = StartLight.RACE
        self._running = False


class ControlUnitState:
    """Simulated state of a Carrera Control Unit."""

    def __init__(self, version="5337"):
        # Car parameters (8 controllers: 0-5 = drivers, 6 = autonomous, 7 = pace car)
        self.fuel = [15] * 8      # Fuel levels (0-15)
        self.speed = [8] * 8      # Speed values (0-15)
        self.brake = [8] * 8      # Brake values (0-15)
        self.position = [0] * 8   # Position tower values (1-8, 0 = not set)

        # Race state
        self.start = 0            # Start light indicator (0-9)
        self.mode = 0             # Mode bitmask
        self.pit = [False] * 8    # Pit lane status
        self.display = 8          # Number of drivers to display (6 or 8)
        self.is_paused = False    # Track if race is paused (vs never started)

        # Timing
        self.timestamp = 0        # Current timestamp in ms
        self.start_time = None    # Real start time for timestamp calculation

        # Version
        self.version = version

        # Timer events queue
        self.timer_events = queue.Queue()

    def get_timestamp(self):
        """Get current timestamp in milliseconds."""
        if self.start_time is None:
            return self.timestamp
        elapsed = int((time.time() - self.start_time) * 1000)
        return (self.timestamp + elapsed) & 0xFFFFFFFF

    def reset_timer(self):
        """Reset the timer to zero."""
        self.timestamp = 0
        self.start_time = time.time()

    def add_timer_event(self, address, sector=1, timestamp=None):
        """Add a timer event to the queue."""
        if timestamp is None:
            timestamp = self.get_timestamp()
        self.timer_events.put(TimerEvent(address, timestamp, sector))

    def has_timer_event(self):
        """Check if there are pending timer events."""
        return not self.timer_events.empty()

    def get_timer_event(self):
        """Get next timer event or None if queue is empty."""
        try:
            return self.timer_events.get_nowait()
        except queue.Empty:
            return None


class RaceSimulator:
    """Simulates cars racing around the track, generating timer events."""

    def __init__(self, state, base_lap_time=5.0, variation=0.5):
        """Initialize race simulator.

        Args:
            state: ControlUnitState to update with timer events.
            base_lap_time: Base lap time in seconds.
            variation: Random variation in lap time (0-1 as fraction).
        """
        self.state = state
        self.base_lap_time = base_lap_time
        self.variation = variation
        self._running = False
        self._thread = None
        self._active_cars = set()  # Cars currently racing
        self._car_next_lap = {}    # Next lap time for each car

    def start(self, cars=None, resume=False):
        """Start the race simulation.

        Args:
            cars: List of car addresses (0-7) to race. Default is [0, 1].
            resume: If True, resume without resetting timer or reinitializing cars.
        """
        if cars is None:
            cars = [0, 1]

        self._active_cars = set(cars)
        self._running = True
        self.state.start = 9  # Race in progress

        if not resume:
            self.state.reset_timer()
            # Initialize next lap times only on fresh start
            for car in cars:
                self._car_next_lap[car] = self._calculate_lap_time(car)
        else:
            # On resume, adjust next lap times based on current timestamp
            current_time = self.state.get_timestamp() / 1000.0
            for car in cars:
                if car not in self._car_next_lap or self._car_next_lap[car] < current_time:
                    self._car_next_lap[car] = current_time + self._calculate_lap_time(car)

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the race simulation."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self):
        """Main simulation loop."""
        while self._running:
            current_time = self.state.get_timestamp() / 1000.0  # Convert to seconds

            for car in list(self._active_cars):
                if car in self._car_next_lap:
                    next_time = self._car_next_lap[car]
                    if current_time >= next_time:
                        # Car crossed finish line
                        timestamp = int(next_time * 1000) & 0xFFFFFFFF
                        self.state.add_timer_event(car, sector=1, timestamp=timestamp)

                        # Schedule next lap
                        self._car_next_lap[car] = next_time + self._calculate_lap_time(car)

                        # Decrease fuel (if fuel mode enabled)
                        if self.state.mode & 0x1:  # FUEL_MODE
                            self.state.fuel[car] = max(0, self.state.fuel[car] - 1)

            time.sleep(0.01)  # 10ms resolution

    def _calculate_lap_time(self, car):
        """Calculate lap time for a car based on its speed."""
        speed = self.state.speed[car]
        if speed == 0:
            return float('inf')  # Car not moving

        # Faster speed = shorter lap time
        speed_factor = 1.0 - (speed / 15.0) * 0.5  # 0.5 to 1.0
        var = random.uniform(-self.variation, self.variation)
        return self.base_lap_time * speed_factor * (1 + var)


class MockConnection(Connection):
    """Mock connection that simulates a Carrera Control Unit."""

    def __init__(self, state=None, red_interval=1.0, green_duration=0.5):
        """Initialize mock connection.

        Args:
            state: Optional ControlUnitState instance. If None, creates a new one.
            red_interval: Time between red light steps in seconds.
            green_duration: How long green light stays on before race starts.
        """
        self.state = state or ControlUnitState()
        self._response_queue = queue.Queue()
        self._startlight_sequence = StartLightSequence(
            self.state,
            red_interval=red_interval,
            green_duration=green_duration
        )
        self._on_race_start = None  # Callback when race starts

    def close(self):
        """Close the connection."""
        self._startlight_sequence.stop()

    def recv(self, maxlength=None):
        """Receive a response from the simulated Control Unit."""
        try:
            response = self._response_queue.get(timeout=1.0)
            if maxlength is not None and len(response) > maxlength:
                response = response[:maxlength]
            return response
        except queue.Empty:
            raise TimeoutError("Timeout waiting for response")

    def send(self, buf, offset=0, size=None):
        """Send a command to the simulated Control Unit."""
        n = len(buf)
        if offset < 0:
            raise ValueError("offset is negative")
        elif n < offset:
            raise ValueError("buffer length < offset")
        elif size is None:
            size = n - offset
        elif size < 0:
            raise ValueError("size is negative")
        elif offset + size > n:
            raise ValueError("buffer length < offset + size")

        data = buf[offset:offset + size]
        response = self._handle_command(data)
        if response is not None:
            self._response_queue.put(response)

    def _handle_command(self, data):
        """Handle a command and return the response."""
        if not data:
            return None

        cmd = data[0:1]

        if cmd == b"?":
            return self._handle_poll()
        elif cmd == b"0":
            return self._handle_version()
        elif cmd == b"J":
            return self._handle_setword(data)
        elif cmd == b"T":
            return self._handle_press(data)
        elif cmd == b"=":
            return self._handle_reset(data)
        elif cmd == b":":
            return self._handle_ignore(data)
        elif cmd == b"G":
            return self._handle_fwu_start(data)
        elif cmd == b"E":
            return self._handle_fwu_write(data)
        else:
            # Echo back unknown commands
            return data

    def _handle_poll(self):
        """Handle poll command (?)."""
        # Check for pending timer events first
        event = self.state.get_timer_event()
        if event:
            # Timer response: ?<address><timestamp><sector><checksum>
            # Address is 1-based in protocol
            return protocol.pack("cYIYC", b"?", event.address + 1, event.timestamp, event.sector)
        else:
            # Status response: ?:<fuel*8><start><mode><pit><display><checksum>
            s = self.state
            pitmask = sum((1 << i) if s.pit[i] else 0 for i in range(8))
            return protocol.pack("cc8YYYBYC", b"?", b":",
                                 *s.fuel, s.start, s.mode, pitmask, s.display)

    def _handle_version(self):
        """Handle version command (0)."""
        return protocol.pack("c4sC", b"0", self.state.version.encode())

    def _handle_setword(self, data):
        """Handle setword command (J)."""
        # Parse: J<word|address<<5><value><repeat><checksum>
        try:
            _, word_addr, value, repeat = protocol.unpack("cBYY", data[:-1])
            word = word_addr & 0x1F
            address = (word_addr >> 5) & 0x07

            # Apply the command based on word type
            if word == 0:  # Speed
                self.state.speed[address] = value
            elif word == 1:  # Brake
                self.state.brake[address] = value
            elif word == 2:  # Fuel
                self.state.fuel[address] = value
            elif word == 6:  # Position
                if value == 9:  # Clear all positions
                    self.state.position = [0] * 8
                else:
                    self.state.position[address] = value
            elif word == 17:  # Lap high nibble
                pass  # Display only, no state change needed
            elif word == 18:  # Lap low nibble
                pass  # Display only, no state change needed

        except (protocol.ProtocolError, ValueError):
            pass

        # Echo back the command
        return data

    def _handle_press(self, data):
        """Handle button press command (T)."""
        try:
            _, button_id = protocol.unpack("cY", data[:-1])

            if button_id == 2:  # START/ENTER
                if self.state.start == StartLight.OFF:
                    if self.state.is_paused:
                        # Resume race instantly without countdown
                        self.state.start = StartLight.RACE
                        self.state.is_paused = False
                    else:
                        # Start the countdown sequence
                        self._startlight_sequence.start(on_race_start=self._on_race_start)
                elif self.state.start == StartLight.RACE:
                    # Pause the race
                    self._startlight_sequence.stop()
                    self.state.start = StartLight.OFF
                    self.state.is_paused = True

            elif button_id == 1:  # PACE CAR/ESC
                # ESC during countdown cancels it
                if self._startlight_sequence.is_running():
                    self._startlight_sequence.stop()
                    self.state.start = StartLight.OFF
                    self.state.is_paused = False

        except (protocol.ProtocolError, ValueError):
            pass

        # Echo back the command
        return data

    def _handle_reset(self, data):
        """Handle reset command (=)."""
        self.state.reset_timer()
        return data

    def _handle_ignore(self, data):
        """Handle ignore command (:)."""
        # Just echo back - we don't actually ignore controllers in mock
        return data

    def _handle_fwu_start(self, data):
        """Handle firmware update start command (G)."""
        return data

    def _handle_fwu_write(self, data):
        """Handle firmware update write command (E)."""
        return data

    max_fwu_block_size = None
