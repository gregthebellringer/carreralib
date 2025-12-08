"""Tests for the mock Control Unit implementation."""

import time
import unittest

from carreralib.cu import ControlUnit
from carreralib.mock import (
    ControlUnitState, MockConnection, RaceSimulator,
    StartLight, StartLightSequence
)


class TestControlUnitState(unittest.TestCase):
    """Tests for ControlUnitState."""

    def test_initial_state(self):
        """Test initial state values."""
        state = ControlUnitState()
        self.assertEqual(state.fuel, [15] * 8)
        self.assertEqual(state.speed, [8] * 8)
        self.assertEqual(state.brake, [8] * 8)
        self.assertEqual(state.start, 0)
        self.assertEqual(state.mode, 0)
        self.assertEqual(state.display, 8)
        self.assertEqual(state.version, "5337")

    def test_custom_version(self):
        """Test custom firmware version."""
        state = ControlUnitState(version="1234")
        self.assertEqual(state.version, "1234")

    def test_timer_events(self):
        """Test timer event queue."""
        state = ControlUnitState()
        self.assertFalse(state.has_timer_event())
        self.assertIsNone(state.get_timer_event())

        state.add_timer_event(0, sector=1, timestamp=1000)
        self.assertTrue(state.has_timer_event())

        event = state.get_timer_event()
        self.assertEqual(event.address, 0)
        self.assertEqual(event.timestamp, 1000)
        self.assertEqual(event.sector, 1)

        self.assertFalse(state.has_timer_event())

    def test_reset_timer(self):
        """Test timer reset."""
        state = ControlUnitState()
        state.timestamp = 5000
        state.reset_timer()
        # After reset, timestamp should be close to 0
        self.assertLess(state.get_timestamp(), 100)


class TestMockConnection(unittest.TestCase):
    """Tests for MockConnection."""

    def test_version_command(self):
        """Test version command (0)."""
        mock = MockConnection()
        mock.send(b"0")
        response = mock.recv()
        self.assertTrue(response.startswith(b"0"))
        self.assertIn(b"5337", response)

    def test_poll_status(self):
        """Test poll command returning status (?)."""
        mock = MockConnection()
        mock.send(b"?")
        response = mock.recv()
        self.assertTrue(response.startswith(b"?:"))

    def test_poll_timer_event(self):
        """Test poll command returning timer event."""
        mock = MockConnection()
        mock.state.add_timer_event(0, sector=1, timestamp=1000)
        mock.send(b"?")
        response = mock.recv()
        # Timer response starts with ? but not ?:
        self.assertTrue(response.startswith(b"?"))
        self.assertFalse(response.startswith(b"?:"))

    def test_setword_speed(self):
        """Test setting speed via setword (J)."""
        mock = MockConnection()
        # Use ControlUnit to generate proper command
        cu = ControlUnit(mock)
        cu.setspeed(0, 15)
        self.assertEqual(mock.state.speed[0], 15)

    def test_setword_brake(self):
        """Test setting brake via setword (J)."""
        mock = MockConnection()
        cu = ControlUnit(mock)
        cu.setbrake(1, 10)
        self.assertEqual(mock.state.brake[1], 10)

    def test_setword_fuel(self):
        """Test setting fuel via setword (J)."""
        mock = MockConnection()
        cu = ControlUnit(mock)
        cu.setfuel(2, 5)
        self.assertEqual(mock.state.fuel[2], 5)

    def test_reset_command(self):
        """Test reset command (=)."""
        mock = MockConnection()
        mock.state.timestamp = 10000
        cu = ControlUnit(mock)
        cu.reset()
        # Timestamp should be reset
        self.assertLess(mock.state.get_timestamp(), 100)


class TestControlUnitWithMock(unittest.TestCase):
    """Integration tests for ControlUnit with MockConnection."""

    def test_version(self):
        """Test getting version."""
        mock = MockConnection()
        cu = ControlUnit(mock)
        version = cu.version()
        self.assertEqual(version, "5337")

    def test_poll_status(self):
        """Test polling for status."""
        mock = MockConnection()
        cu = ControlUnit(mock)
        status = cu.poll()
        self.assertIsInstance(status, ControlUnit.Status)
        self.assertEqual(len(status.fuel), 8)
        self.assertEqual(status.display, 8)

    def test_poll_timer(self):
        """Test polling for timer events."""
        mock = MockConnection()
        mock.state.add_timer_event(2, sector=1, timestamp=5000)
        cu = ControlUnit(mock)
        timer = cu.poll()
        self.assertIsInstance(timer, ControlUnit.Timer)
        self.assertEqual(timer.address, 2)
        self.assertEqual(timer.timestamp, 5000)
        self.assertEqual(timer.sector, 1)

    def test_start(self):
        """Test start command."""
        mock = MockConnection(red_interval=0.02, green_duration=0.02)
        cu = ControlUnit(mock)
        cu.start()
        # Start button was pressed, sequence should be running
        time.sleep(0.05)  # Wait past initial pause
        self.assertGreater(mock.state.start, 0)

    def test_setpos(self):
        """Test setting position."""
        mock = MockConnection()
        cu = ControlUnit(mock)
        cu.setpos(0, 1)
        self.assertEqual(mock.state.position[0], 1)

    def test_clrpos(self):
        """Test clearing positions."""
        mock = MockConnection()
        mock.state.position = [1, 2, 3, 4, 5, 6, 7, 8]
        cu = ControlUnit(mock)
        cu.clrpos()
        self.assertEqual(mock.state.position, [0] * 8)


class TestStartLightSequence(unittest.TestCase):
    """Tests for StartLightSequence."""

    def test_startlight_constants(self):
        """Test startlight state constants."""
        self.assertEqual(StartLight.OFF, 0)
        self.assertEqual(StartLight.RED_1, 1)
        self.assertEqual(StartLight.RED_2, 2)
        self.assertEqual(StartLight.RED_3, 3)
        self.assertEqual(StartLight.RED_4, 4)
        self.assertEqual(StartLight.RED_5, 5)
        self.assertEqual(StartLight.RED_ALL, 6)
        self.assertEqual(StartLight.GREEN, 7)
        self.assertEqual(StartLight.RACE, 9)

    def test_sequence_full_countdown(self):
        """Test full countdown sequence from OFF to RACE."""
        state = ControlUnitState()
        seq = StartLightSequence(state, red_interval=0.02, green_duration=0.02)

        self.assertEqual(state.start, StartLight.OFF)
        seq.start()

        # Wait for sequence to complete (initial pause + 6 red steps + green + race)
        time.sleep(0.4)

        self.assertEqual(state.start, StartLight.RACE)
        self.assertFalse(seq.is_running())

    def test_sequence_progresses_through_red_lights(self):
        """Test that sequence progresses through all red light states."""
        state = ControlUnitState()
        seq = StartLightSequence(state, red_interval=0.05, green_duration=0.05)

        observed_states = []

        seq.start()

        # Sample states during countdown
        for _ in range(20):
            if state.start not in observed_states:
                observed_states.append(state.start)
            time.sleep(0.02)

        seq.stop()

        # Should have seen red lights counting up
        self.assertIn(StartLight.RED_1, observed_states)
        self.assertIn(StartLight.RED_ALL, observed_states)

    def test_sequence_green_light(self):
        """Test that green light appears in sequence."""
        state = ControlUnitState()
        seq = StartLightSequence(state, red_interval=0.02, green_duration=0.1)

        seq.start()

        # Wait for red lights (6 * 0.02 = 0.12s)
        time.sleep(0.15)

        # Should be at green or race state
        self.assertIn(state.start, [StartLight.GREEN, StartLight.RACE])

        seq.stop()

    def test_sequence_can_be_stopped(self):
        """Test that sequence can be stopped mid-countdown."""
        state = ControlUnitState()
        seq = StartLightSequence(state, red_interval=0.1, green_duration=0.1)

        seq.start()
        time.sleep(0.05)

        self.assertTrue(seq.is_running())
        seq.stop()
        self.assertFalse(seq.is_running())

    def test_sequence_timer_reset_at_green(self):
        """Test that timer is reset when green light appears."""
        state = ControlUnitState()
        state.timestamp = 99999  # Set a high timestamp
        seq = StartLightSequence(state, red_interval=0.02, green_duration=0.02)

        seq.start()
        time.sleep(0.3)  # Wait for sequence to complete (initial + 6 red + green)

        # Timer should have been reset near zero
        self.assertLess(state.get_timestamp(), 500)

    def test_sequence_callback_on_race_start(self):
        """Test that callback is called when race starts."""
        state = ControlUnitState()
        seq = StartLightSequence(state, red_interval=0.02, green_duration=0.02)

        callback_called = []

        def on_start():
            callback_called.append(True)

        seq.start(on_race_start=on_start)
        time.sleep(0.4)  # initial pause + 6 red + green

        self.assertEqual(len(callback_called), 1)

    def test_sequence_does_not_restart_while_running(self):
        """Test that calling start while running does nothing."""
        state = ControlUnitState()
        seq = StartLightSequence(state, red_interval=0.1, green_duration=0.1)

        seq.start()
        time.sleep(0.05)
        initial_state = state.start

        # Try to start again
        seq.start()

        # Should still be in the same sequence
        self.assertTrue(seq.is_running())
        self.assertEqual(state.start, initial_state)

        seq.stop()


class TestMockConnectionStartLight(unittest.TestCase):
    """Tests for MockConnection startlight integration."""

    def test_start_button_triggers_sequence(self):
        """Test that START button triggers the countdown sequence."""
        mock = MockConnection(red_interval=0.02, green_duration=0.02)
        cu = ControlUnit(mock)

        self.assertEqual(mock.state.start, StartLight.OFF)

        cu.start()  # Press START button

        # Sequence should have started (wait past initial pause)
        time.sleep(0.05)
        self.assertGreater(mock.state.start, StartLight.OFF)

        # Wait for completion (initial pause + 6 red + green + race)
        time.sleep(0.4)
        self.assertEqual(mock.state.start, StartLight.RACE)

    def test_esc_cancels_countdown(self):
        """Test that ESC button cancels the countdown."""
        mock = MockConnection(red_interval=0.05, green_duration=0.05)
        cu = ControlUnit(mock)

        cu.start()  # Start countdown
        time.sleep(0.15)  # Wait past initial pause + first light

        # Should be in countdown
        self.assertGreater(mock.state.start, StartLight.OFF)

        cu.press(ControlUnit.PACE_CAR_ESC_BUTTON_ID)  # Cancel with ESC

        # Should be back to OFF
        self.assertEqual(mock.state.start, StartLight.OFF)

    def test_start_during_race_pauses(self):
        """Test that START during race pauses (returns to OFF)."""
        mock = MockConnection(red_interval=0.02, green_duration=0.02)
        cu = ControlUnit(mock)

        cu.start()
        time.sleep(0.4)  # Wait for race to start (initial pause + 6 red + green)

        self.assertEqual(mock.state.start, StartLight.RACE)

        cu.start()  # Press START again to pause

        self.assertEqual(mock.state.start, StartLight.OFF)


class TestRaceSimulator(unittest.TestCase):
    """Tests for RaceSimulator."""

    def test_start_stop(self):
        """Test starting and stopping simulation."""
        state = ControlUnitState()
        sim = RaceSimulator(state, base_lap_time=0.1)

        self.assertEqual(state.start, 0)
        sim.start(cars=[0])
        self.assertEqual(state.start, 9)  # Race in progress

        time.sleep(0.05)
        sim.stop()
        self.assertEqual(state.start, 0)

    def test_generates_timer_events(self):
        """Test that simulation generates timer events."""
        state = ControlUnitState()
        state.speed[0] = 15  # Max speed for fastest laps
        sim = RaceSimulator(state, base_lap_time=0.1, variation=0)

        sim.start(cars=[0])
        time.sleep(0.3)  # Wait for a few laps
        sim.stop()

        # Should have generated at least one timer event
        self.assertTrue(state.has_timer_event())


if __name__ == "__main__":
    unittest.main()
