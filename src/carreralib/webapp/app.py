"""FastAPI application for Carrera Race Management."""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from ..cu import ControlUnit
from ..mock import MockConnection, ControlUnitState, RaceSimulator

logger = logging.getLogger(__name__)

# Get the directory containing this file
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


class RaceManager:
    """Manages the race state and Control Unit connection."""

    def __init__(self):
        self.cu: Optional[ControlUnit] = None
        self.connected = False
        self.device_url: Optional[str] = None
        self.mock_state: Optional[ControlUnitState] = None
        self.simulator: Optional[RaceSimulator] = None
        self.use_mock = False

        # Race tracking
        self.cars = {}  # address -> car data
        self.pace_car_deployed = False
        self.last_start_light = 0  # Track last known start light state
        self.race_has_started = False  # Track if race has ever started

        # Initialize car data for 8 controllers
        for i in range(8):
            self.cars[i] = {
                "address": i,
                "position": i + 1,
                "laps": 0,
                "last_lap_time": 0,
                "best_lap_time": 0,
                "fuel": 15,
                "in_pit": False,
                "last_timestamp": 0
            }

    def connect(self, device_url: str = None, use_mock: bool = False):
        """Connect to the Control Unit."""
        if self.connected:
            self.disconnect()

        try:
            if use_mock:
                self.mock_state = ControlUnitState()
                self.cu = ControlUnit(MockConnection(self.mock_state))
                self.simulator = RaceSimulator(self.mock_state)
                self.use_mock = True
                logger.info("Connected to mock Control Unit")
            else:
                self.device_url = device_url or "socket://localhost:5000"
                self.cu = ControlUnit(self.device_url)
                self.use_mock = False
                logger.info(f"Connected to Control Unit at {self.device_url}")

            self.connected = True
            self._reset_race_data()
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from the Control Unit."""
        if self.simulator:
            self.simulator.stop()
            self.simulator = None
        if self.cu:
            try:
                self.cu.close()
            except Exception:
                pass
            self.cu = None
        self.connected = False
        self.mock_state = None
        logger.info("Disconnected from Control Unit")

    def _reset_race_data(self):
        """Reset race tracking data."""
        for i in range(8):
            self.cars[i] = {
                "address": i,
                "position": i + 1,
                "laps": 0,
                "last_lap_time": 0,
                "best_lap_time": 0,
                "fuel": 15,
                "in_pit": False,
                "last_timestamp": 0
            }
        self.pace_car_deployed = False
        self.last_start_light = 0
        self.race_has_started = False

    def start_race(self):
        """Start or resume the race."""
        if not self.connected or not self.cu:
            return False
        try:
            is_resume = self.race_has_started and self.last_start_light == 0
            self.cu.start()
            self.race_has_started = True
            if self.use_mock and self.simulator:
                # Start simulation with cars 0-3 (resume=True if resuming)
                self.simulator.start(cars=[0, 1, 2, 3], resume=is_resume)
            return True
        except Exception as e:
            logger.error(f"Failed to start race: {e}")
            return False

    def pause_race(self):
        """Pause the race."""
        if not self.connected or not self.cu:
            return False
        try:
            self.cu.start()  # Toggle pause
            if self.use_mock and self.simulator:
                self.simulator.stop()
            return True
        except Exception as e:
            logger.error(f"Failed to pause race: {e}")
            return False

    def stop_race(self):
        """Stop the race completely, resetting all timers and lap counts."""
        if not self.connected or not self.cu:
            return False
        try:
            # Pause if currently racing
            if self.last_start_light > 0:
                self.cu.start()  # Toggle to pause
            if self.use_mock and self.simulator:
                self.simulator.stop()
            # Reset all race data
            self._reset_race_data()
            return True
        except Exception as e:
            logger.error(f"Failed to stop race: {e}")
            return False

    def deploy_pace_car(self):
        """Deploy the pace car."""
        if not self.connected or not self.cu:
            return False
        try:
            self.cu.press(ControlUnit.PACE_CAR_ESC_BUTTON_ID)
            self.pace_car_deployed = True
            return True
        except Exception as e:
            logger.error(f"Failed to deploy pace car: {e}")
            return False

    def recall_pace_car(self):
        """Recall the pace car."""
        if not self.connected or not self.cu:
            return False
        try:
            self.cu.press(ControlUnit.PACE_CAR_ESC_BUTTON_ID)
            self.pace_car_deployed = False
            return True
        except Exception as e:
            logger.error(f"Failed to recall pace car: {e}")
            return False

    def poll(self):
        """Poll the Control Unit for status/timer events."""
        if not self.connected or not self.cu:
            return None
        try:
            return self.cu.poll()
        except Exception as e:
            logger.error(f"Poll error: {e}")
            return None

    def get_status(self):
        """Get current race status."""
        status_data = {
            "connected": self.connected,
            "start_light": self.last_start_light,  # Use last known value
            "mode": 0,
            "pace_car_deployed": self.pace_car_deployed,
            "race_has_started": self.race_has_started,
            "cars": []
        }

        if self.connected and self.cu:
            try:
                result = self.poll()
                if isinstance(result, ControlUnit.Status):
                    self.last_start_light = result.start  # Store for next time
                    status_data["start_light"] = result.start
                    status_data["mode"] = result.mode
                    # Update fuel levels
                    for i, fuel in enumerate(result.fuel):
                        self.cars[i]["fuel"] = fuel
                        self.cars[i]["in_pit"] = result.pit[i]
                elif isinstance(result, ControlUnit.Timer):
                    self._process_timer_event(result)
                    # Keep last known start_light value (already set above)
            except Exception as e:
                logger.error(f"Error getting status: {e}")

        # Sort cars by position
        sorted_cars = sorted(self.cars.values(), key=lambda x: (-(x["laps"]), x["last_timestamp"]))
        for pos, car in enumerate(sorted_cars):
            car["position"] = pos + 1

        status_data["cars"] = sorted_cars[:6]  # Only show first 6 cars
        return status_data

    def _process_timer_event(self, timer):
        """Process a timer event and update car data."""
        car = self.cars.get(timer.address)
        if not car:
            return

        if timer.sector == 1:  # Finish line
            # Calculate lap time
            if car["last_timestamp"] > 0:
                lap_time = timer.timestamp - car["last_timestamp"]
                car["last_lap_time"] = lap_time
                if car["best_lap_time"] == 0 or lap_time < car["best_lap_time"]:
                    car["best_lap_time"] = lap_time

            car["laps"] += 1
            car["last_timestamp"] = timer.timestamp


# Global race manager instance
race_manager = RaceManager()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Carrera Race Management",
        description="Web-based Race Management System for Carrera Digital 124/132",
        version="1.0.0"
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Templates
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """Serve the main page."""
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/api/status")
    async def get_status():
        """Get current race status."""
        return race_manager.get_status()

    @app.post("/api/connect")
    async def connect(device_url: str = None, use_mock: bool = False):
        """Connect to Control Unit."""
        success = race_manager.connect(device_url, use_mock)
        return {"success": success, "connected": race_manager.connected}

    @app.post("/api/disconnect")
    async def disconnect():
        """Disconnect from Control Unit."""
        race_manager.disconnect()
        return {"success": True, "connected": False}

    @app.post("/api/race/start")
    async def start_race():
        """Start the race."""
        success = race_manager.start_race()
        return {"success": success}

    @app.post("/api/race/pause")
    async def pause_race():
        """Pause the race."""
        success = race_manager.pause_race()
        return {"success": success}

    @app.post("/api/race/stop")
    async def stop_race():
        """Stop the race and reset all timers."""
        success = race_manager.stop_race()
        return {"success": success}

    @app.post("/api/pacecar/deploy")
    async def deploy_pace_car():
        """Deploy pace car."""
        success = race_manager.deploy_pace_car()
        return {"success": success, "deployed": race_manager.pace_car_deployed}

    @app.post("/api/pacecar/recall")
    async def recall_pace_car():
        """Recall pace car."""
        success = race_manager.recall_pace_car()
        return {"success": success, "deployed": race_manager.pace_car_deployed}

    @app.websocket("/ws/race")
    async def websocket_race(websocket: WebSocket):
        """WebSocket endpoint for real-time race data."""
        await websocket.accept()
        logger.info("WebSocket client connected")

        try:
            while True:
                # Send status update
                status = race_manager.get_status()
                await websocket.send_json({"type": "status", **status})

                # Small delay between updates
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

    @app.on_event("startup")
    async def startup():
        """Auto-connect on startup (to mock by default)."""
        logger.info("Starting Carrera Race Management Web App")
        # Try to connect to test server, fall back to mock
        if not race_manager.connect("socket://localhost:5000"):
            logger.info("Test server not available, using mock")
            race_manager.connect(use_mock=True)

    @app.on_event("shutdown")
    async def shutdown():
        """Disconnect on shutdown."""
        logger.info("Shutting down Carrera Race Management Web App")
        race_manager.disconnect()

    return app


def main():
    """Run the web application."""
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Carrera Race Management Web App")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--device", "-d", help="Control Unit device URL")
    parser.add_argument("--mock", "-m", action="store_true", help="Use mock Control Unit")
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    print(f"Starting Carrera Race Management Web App")
    print(f"Open http://localhost:{args.port} in your browser")
    print()

    uvicorn.run(
        "carreralib.webapp.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload
    )


if __name__ == "__main__":
    main()
