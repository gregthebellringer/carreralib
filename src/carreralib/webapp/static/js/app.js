/**
 * Carrera Race Management - Frontend Application
 */

class RaceApp {
    constructor() {
        // State
        this.connected = false;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.paceCarDeployed = false;
        this.currentStartLightState = 0;
        this.raceHasStarted = false;

        // DOM Elements
        this.elements = {
            connectionStatus: document.getElementById('connectionStatus'),
            deviceUrl: document.getElementById('deviceUrl'),
            btnConnect: document.getElementById('btnConnect'),
            btnDisconnect: document.getElementById('btnDisconnect'),
            btnMock: document.getElementById('btnMock'),
            btnStart: document.getElementById('btnStart'),
            btnPause: document.getElementById('btnPause'),
            btnStop: document.getElementById('btnStop'),
            btnPaceCar: document.getElementById('btnPaceCar'),
            paceCarText: document.getElementById('paceCarText'),
            pauseText: document.getElementById('pauseText'),
            raceButtonGroup: document.getElementById('raceButtonGroup'),
            startLights: document.getElementById('startLights'),
            lightStatus: document.getElementById('lightStatus'),
            standingsList: document.getElementById('standingsList')
        };

        // Bind event handlers
        this.bindEvents();

        // Start WebSocket connection
        this.connectWebSocket();
    }

    bindEvents() {
        this.elements.btnConnect.addEventListener('click', () => this.connect());
        this.elements.btnDisconnect.addEventListener('click', () => this.disconnect());
        this.elements.btnMock.addEventListener('click', () => this.connectMock());
        this.elements.btnStart.addEventListener('click', () => this.startRace());
        this.elements.btnPause.addEventListener('click', () => this.pauseRace());
        this.elements.btnStop.addEventListener('click', () => this.stopRace());
        this.elements.btnPaceCar.addEventListener('click', () => this.togglePaceCar());
    }

    // API Methods
    async apiCall(endpoint, method = 'POST', body = null) {
        try {
            const options = {
                method,
                headers: { 'Content-Type': 'application/json' }
            };
            if (body) {
                options.body = JSON.stringify(body);
            }
            const response = await fetch(`/api${endpoint}`, options);
            return await response.json();
        } catch (error) {
            console.error(`API error (${endpoint}):`, error);
            return { success: false, error: error.message };
        }
    }

    async connect() {
        const deviceUrl = this.elements.deviceUrl.value || 'socket://localhost:5000';
        const result = await this.apiCall(`/connect?device_url=${encodeURIComponent(deviceUrl)}`);
        if (result.success) {
            this.raceHasStarted = false;
            this.setConnected(true);
        }
    }

    async disconnect() {
        const result = await this.apiCall('/disconnect');
        if (result.success) {
            this.raceHasStarted = false;
            this.setConnected(false);
        }
    }

    async connectMock() {
        const result = await this.apiCall('/connect?use_mock=true');
        if (result.success) {
            this.raceHasStarted = false;
            this.setConnected(true);
        }
    }

    async startRace() {
        await this.apiCall('/race/start');
    }

    async pauseRace() {
        await this.apiCall('/race/pause');
    }

    async stopRace() {
        const result = await this.apiCall('/race/stop');
        if (result.success) {
            this.raceHasStarted = false;
        }
    }

    async togglePaceCar() {
        if (this.paceCarDeployed) {
            const result = await this.apiCall('/pacecar/recall');
            if (result.success) {
                this.paceCarDeployed = false;
                this.updatePaceCarButton();
                this.updateStartLights(this.currentStartLightState);
            }
        } else {
            const result = await this.apiCall('/pacecar/deploy');
            if (result.success) {
                this.paceCarDeployed = true;
                this.updatePaceCarButton();
                this.updateStartLights(this.currentStartLightState);
            }
        }
    }

    // WebSocket
    connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/race`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            } catch (error) {
                console.error('WebSocket message error:', error);
            }
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.scheduleReconnect();
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * this.reconnectAttempts;
            console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
            setTimeout(() => this.connectWebSocket(), delay);
        }
    }

    handleWebSocketMessage(data) {
        if (data.type === 'status') {
            // Update state variables first, before any UI updates
            this.paceCarDeployed = data.pace_car_deployed;
            this.currentStartLightState = data.start_light;
            this.raceHasStarted = data.race_has_started || false;

            // Now update UI
            this.setConnected(data.connected);
            this.updatePaceCarButton();
            this.updateStartLights(data.start_light);
            this.updateRaceButtons(data.start_light);
            this.updateStandings(data.cars);
        } else if (data.type === 'timer') {
            // Timer events are already processed server-side
        }
    }

    // UI Updates
    setConnected(connected) {
        this.connected = connected;

        // Update status indicator
        const statusDot = this.elements.connectionStatus.querySelector('.status-dot');
        const statusText = this.elements.connectionStatus.querySelector('.status-text');

        if (connected) {
            statusDot.classList.remove('disconnected');
            statusDot.classList.add('connected');
            statusText.textContent = 'Connected';
        } else {
            statusDot.classList.remove('connected');
            statusDot.classList.add('disconnected');
            statusText.textContent = 'Disconnected';
        }

        // Update connection buttons
        this.elements.btnConnect.disabled = connected;
        this.elements.btnMock.disabled = connected;
        this.elements.btnDisconnect.disabled = !connected;

        // Update race buttons based on connection state
        // Use currentStartLightState instead of hardcoded 0
        this.updateRaceButtons(this.currentStartLightState);
    }

    updateStartLights(state) {
        const lights = this.elements.startLights.querySelectorAll('.light');
        const lightStatus = this.elements.lightStatus;

        // Reset all lights
        lights.forEach(light => {
            light.classList.remove('red', 'green', 'yellow', 'blink');
        });
        lightStatus.classList.remove('go');

        // Check if pace car is deployed - show blinking yellow
        if (this.paceCarDeployed) {
            lights.forEach(light => {
                light.classList.add('yellow', 'blink');
            });
            lightStatus.textContent = 'Pace Car Deployed';
            return;
        }

        if (state === 0) {
            // Show blinking red if race is paused, otherwise empty
            if (this.raceHasStarted) {
                lights.forEach(light => {
                    light.classList.add('red', 'blink');
                });
                lightStatus.textContent = 'Race is paused';
            } else {
                lightStatus.textContent = '';
            }
        } else if (state >= 1 && state <= 5) {
            // Red lights countdown
            for (let i = 0; i < state; i++) {
                lights[i].classList.add('red');
            }
            lightStatus.textContent = `Countdown: ${6 - state}`;
        } else if (state === 6) {
            // All red lights
            lights.forEach(light => light.classList.add('red'));
            lightStatus.textContent = 'GET READY!';
        } else if (state === 7) {
            // Green light - GO!
            lights.forEach(light => light.classList.add('green'));
            lightStatus.textContent = 'GO! GO! GO!';
            lightStatus.classList.add('go');
        } else if (state >= 8) {
            // Race in progress - no text needed
            lightStatus.textContent = '';
        }
    }

    updateStandings(cars) {
        if (!cars || cars.length === 0) {
            this.elements.standingsList.innerHTML = '<div class="no-data">No cars racing</div>';
            return;
        }

        const html = cars.map((car, index) => {
            const positionClass = index === 0 ? 'p1' : index === 1 ? 'p2' : index === 2 ? 'p3' : '';
            const fuelPercent = (car.fuel / 15) * 100;
            const fuelClass = fuelPercent <= 20 ? 'critical' : fuelPercent <= 40 ? 'low' : '';
            const lastLap = car.last_lap_time > 0 ? this.formatTime(car.last_lap_time) : '--:--.---';
            const bestLap = car.best_lap_time > 0 ? this.formatTime(car.best_lap_time) : '--:--.---';

            return `
                <div class="car-row" data-address="${car.address}">
                    <div class="car-position ${positionClass}">${car.position}</div>
                    <div class="car-info">
                        <div class="car-name">Car ${car.address + 1}</div>
                        <div class="car-stats">
                            <span>Lap ${car.laps}</span>
                            <span>Last: ${lastLap}</span>
                            <span>Best: ${bestLap}</span>
                        </div>
                    </div>
                    <div class="car-fuel">
                        ${car.in_pit ? '<span class="pit-indicator">PIT</span>' : ''}
                        <div class="fuel-bar">
                            <div class="fuel-level ${fuelClass}" style="width: ${fuelPercent}%"></div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        this.elements.standingsList.innerHTML = html;
    }

    updatePaceCarButton() {
        if (this.paceCarDeployed) {
            this.elements.paceCarText.textContent = 'Recall Pace Car';
            this.elements.btnPaceCar.classList.add('btn-warning');
            this.elements.btnPaceCar.classList.remove('btn-info');
        } else {
            this.elements.paceCarText.textContent = 'Deploy Pace Car';
            this.elements.btnPaceCar.classList.add('btn-info');
            this.elements.btnPaceCar.classList.remove('btn-warning');
        }
    }

    updateRaceButtons(startLightState) {
        const { btnStart, btnPause, btnStop, btnPaceCar, pauseText, raceButtonGroup } = this.elements;

        if (!this.connected) {
            // All disabled and hidden when not connected
            btnStart.disabled = true;
            btnPause.disabled = true;
            btnStop.disabled = true;
            btnPaceCar.disabled = true;
            btnStart.classList.add('hidden');
            raceButtonGroup.classList.add('hidden');
        } else if (startLightState === 0 && !this.raceHasStarted) {
            // Not started yet - only show big Start Race button
            btnStart.classList.remove('hidden');
            btnStart.disabled = false;
            raceButtonGroup.classList.add('hidden');
        } else if (startLightState === 0 && this.raceHasStarted) {
            // Paused - show Resume and Stop (no Pace Car when paused)
            btnStart.classList.add('hidden');
            raceButtonGroup.classList.remove('hidden');
            btnPause.disabled = false;
            pauseText.textContent = 'Resume Race';
            btnStop.disabled = false;
            btnPaceCar.classList.add('hidden');
            btnPaceCar.disabled = true;
        } else {
            // Race in progress (countdown, green, or racing) - show Pause, Stop, Pace Car
            btnStart.classList.add('hidden');
            raceButtonGroup.classList.remove('hidden');
            btnPause.disabled = false;
            pauseText.textContent = 'Pause Race';
            btnStop.disabled = false;
            btnPaceCar.classList.remove('hidden');
            btnPaceCar.disabled = false;
        }
    }

    formatTime(ms) {
        if (ms <= 0) return '--:--.---';
        const totalSeconds = ms / 1000;
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return `${minutes}:${seconds.toFixed(3).padStart(6, '0')}`;
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.raceApp = new RaceApp();
});
