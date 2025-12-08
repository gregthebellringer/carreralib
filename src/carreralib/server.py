"""TCP server simulating a Carrera Control Unit."""

import argparse
import logging
import selectors
import socket
import threading
import time

from .mock import ControlUnitState, MockConnection, RaceSimulator

logger = logging.getLogger(__name__)


class ControlUnitServer:
    """TCP server that simulates a Carrera Control Unit.

    The server speaks the Carrera serial protocol over TCP. Clients can connect
    using pyserial's socket:// URL scheme:

        cu = ControlUnit('socket://localhost:5000')

    """

    def __init__(self, host="localhost", port=5000, state=None, simulate=False):
        """Initialize the server.

        Args:
            host: Host address to bind to.
            port: Port number to listen on.
            state: Optional ControlUnitState instance to use.
            simulate: If True, automatically simulate racing cars.
        """
        self.host = host
        self.port = port
        self.state = state or ControlUnitState()
        self._socket = None
        self._selector = None
        self._running = False
        self._thread = None
        self._simulator = RaceSimulator(self.state) if simulate else None

    def start(self, background=True):
        """Start the server.

        Args:
            background: If True, run server in a background thread.
        """
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.host, self.port))
        self._socket.listen(5)
        self._socket.setblocking(False)

        self._selector = selectors.DefaultSelector()
        self._selector.register(self._socket, selectors.EVENT_READ, self._accept)

        self._running = True
        logger.info("Control Unit server listening on %s:%d", self.host, self.port)

        if background:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            self._run()

    def stop(self):
        """Stop the server."""
        self._running = False
        if self._simulator:
            self._simulator.stop()
        if self._selector:
            self._selector.close()
        if self._socket:
            self._socket.close()
        if self._thread:
            self._thread.join(timeout=1.0)
        logger.info("Control Unit server stopped")

    def start_simulation(self, cars=None):
        """Start race simulation with specified cars.

        Args:
            cars: List of car addresses (0-7) to race. Default is [0, 1].
        """
        if self._simulator:
            self._simulator.start(cars)

    def stop_simulation(self):
        """Stop race simulation."""
        if self._simulator:
            self._simulator.stop()

    def _run(self):
        """Main server loop."""
        while self._running:
            try:
                events = self._selector.select(timeout=0.1)
                for key, mask in events:
                    callback = key.data
                    callback(key.fileobj)
            except Exception as e:
                if self._running:
                    logger.error("Server error: %s", e)

    def _accept(self, sock):
        """Accept a new client connection."""
        try:
            conn, addr = sock.accept()
            conn.setblocking(False)
            logger.info("Client connected from %s:%d", *addr)

            # Create a client handler with shared state
            handler = ClientHandler(conn, self.state)
            self._selector.register(conn, selectors.EVENT_READ, handler.handle)
        except Exception as e:
            logger.error("Accept error: %s", e)


class ClientHandler:
    """Handles a single client connection."""

    def __init__(self, conn, state):
        """Initialize client handler.

        Args:
            conn: Client socket connection.
            state: Shared ControlUnitState instance.
        """
        self.conn = conn
        self.mock = MockConnection(state)
        self._buffer = bytearray()

    def handle(self, sock):
        """Handle data from client."""
        try:
            data = sock.recv(1024)
            if not data:
                self._close(sock)
                return

            self._buffer.extend(data)
            self._process_buffer(sock)

        except ConnectionResetError:
            self._close(sock)
        except Exception as e:
            logger.error("Client error: %s", e)
            self._close(sock)

    def _process_buffer(self, sock):
        """Process buffered data and handle complete messages."""
        while True:
            # Look for message start (")
            start_idx = self._buffer.find(b'"')
            if start_idx == -1:
                self._buffer.clear()
                return

            # Discard anything before start
            if start_idx > 0:
                del self._buffer[:start_idx]

            # Look for message end ($ or #)
            end_idx = -1
            for i, b in enumerate(self._buffer):
                if b == ord('$') or b == ord('#'):
                    end_idx = i
                    break

            if end_idx == -1:
                return  # Wait for more data

            # Extract message (without framing characters)
            message = bytes(self._buffer[1:end_idx])
            del self._buffer[:end_idx + 1]

            # Process message
            self._handle_message(sock, message)

    def _handle_message(self, sock, message):
        """Handle a complete message."""
        logger.debug("Received: %r", message)

        # Send to mock connection
        self.mock.send(message)

        # Get response
        try:
            response = self.mock.recv()
            if response:
                # Send response with framing
                framed = b'"' + response + b'$'
                sock.sendall(framed)
                logger.debug("Sent: %r", response)
        except Exception as e:
            logger.error("Response error: %s", e)

    def _close(self, sock):
        """Close client connection."""
        try:
            addr = sock.getpeername()
            logger.info("Client disconnected from %s:%d", *addr)
        except:
            pass
        sock.close()


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Carrera Control Unit Test Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:

  # Start server on default port (5000)
  python -m carreralib.server

  # Start server on custom port
  python -m carreralib.server --port 5001

  # Connect from your application
  from carreralib import ControlUnit
  cu = ControlUnit('socket://localhost:5000')
        """
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host address to bind to (default: localhost)"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=5000,
        help="Port number to listen on (default: 5000)"
    )
    parser.add_argument(
        "--version", "-V",
        default="5337",
        help="Firmware version to report (default: 5337)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--simulate", "-s",
        action="store_true",
        help="Enable race simulation (generates timer events)"
    )
    parser.add_argument(
        "--cars",
        type=str,
        default="0,1",
        help="Comma-separated car addresses to simulate (default: 0,1)"
    )
    parser.add_argument(
        "--lap-time",
        type=float,
        default=5.0,
        help="Base lap time in seconds (default: 5.0)"
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Parse cars list
    cars = [int(c.strip()) for c in args.cars.split(",")]

    # Create and start server
    state = ControlUnitState(version=args.version)
    server = ControlUnitServer(
        host=args.host,
        port=args.port,
        state=state,
        simulate=args.simulate
    )

    # Update simulator settings if enabled
    if args.simulate and server._simulator:
        server._simulator.base_lap_time = args.lap_time

    print(f"Starting Carrera Control Unit Test Server on {args.host}:{args.port}")
    print(f"Firmware version: {args.version}")
    if args.simulate:
        print(f"Simulation: enabled (cars: {cars}, lap time: {args.lap_time}s)")
    print("Press Ctrl+C to stop")
    print()
    print("Connect with:")
    print(f"  cu = ControlUnit('socket://{args.host}:{args.port}')")
    print()

    try:
        server.start(background=True)

        # Start simulation if enabled
        if args.simulate:
            server.start_simulation(cars)

        # Wait for interrupt
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.stop()


if __name__ == "__main__":
    main()
