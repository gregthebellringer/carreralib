"""Tests for the mock Control Unit implementation."""

import time
import unittest

from carreralib.cu import ControlUnit
from carreralib.mock import ControlUnitState, MockConnection, RaceSimulator


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
        mock = MockConnection()
        cu = ControlUnit(mock)
        cu.start()
        # Start button was pressed, start light should advance
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
