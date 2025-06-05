// Main Dashboard JavaScript for Industrial IoT Monitor

class DashboardApp {
    constructor() {
        this.websocket = null;
        this.reconnectInterval = 5000;
        this.maxReconnectAttempts = 10;
        this.reconnectAttempts = 0;
        this.apiBaseUrl = '';

        this.init();
    }

    init() {
        console.log('🚀 Initializing Industrial IoT Dashboard...');

        // Initialize WebSocket connection
        this.connectWebSocket();

        // Load initial data
        this.loadInitialData();

        // Set up periodic data refresh as fallback
        this.setupDataRefresh();

        console.log('✅ Dashboard initialized');
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        try {
            this.websocket = new WebSocket(wsUrl);

            this.websocket.onopen = () => {
                console.log('🔌 WebSocket connected');
                this.updateConnectionStatus(true);
                this.reconnectAttempts = 0;
            };

            this.websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };

            this.websocket.onclose = () => {
                console.log('❌ WebSocket disconnected');
                this.updateConnectionStatus(false);
                this.scheduleReconnect();
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateConnectionStatus(false);
            };

        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.updateConnectionStatus(false);
            this.scheduleReconnect();
        }
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`⏰ Scheduling reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${this.reconnectInterval / 1000}s`);

            setTimeout(() => {
                this.connectWebSocket();
            }, this.reconnectInterval);
        } else {
            console.error('❌ Max reconnect attempts reached');
        }
    }

    handleWebSocketMessage(data) {
        if (data.type === 'live_update') {
            this.updateKPIs(data);
            this.updateMachineGrid(data.machines);
            this.updateEventsTable(data.recent_events);
            this.updateCharts(data.machines);
            this.updateLastUpdateTime();
        }
    }

    updateConnectionStatus(connected) {
        const statusElement = document.getElementById('connectionStatus');
        if (connected) {
            statusElement.innerHTML = '🟢 Connected';
            statusElement.className = 'connection-status connected';
        } else {
            statusElement.innerHTML = '🔴 Disconnected';
            statusElement.className = 'connection-status error';
        }
    }

    async loadInitialData() {
        try {
            // Load overview data
            const response = await fetch(`${this.apiBaseUrl}/api/overview`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            this.updateKPIs(data);
            this.updateMachineGrid(data.machines);
            this.updateEventsTable(data.recent_events);

            // Load sensor data for charts
            this.loadChartData();
            this.updateLastUpdateTime();

        } catch (error) {
            console.error('Error loading initial data:', error);
            this.showError('Failed to load dashboard data');
        }
    }

    updateKPIs(data) {
        if (data.kpis) {
            // Active Machines
            document.getElementById('active-machines').innerHTML =
                `<span class="status-info">${data.kpis.active_machines}/${data.kpis.total_machines}</span>`;

            // Total Power
            document.getElementById('total-power').innerHTML =
                `<span class="status-info">${data.kpis.total_power} kW</span>`;

            // Average Temperature
            const avgTemp = data.kpis.avg_temperature;
            let tempClass = 'status-info';
            if (avgTemp > 80) tempClass = 'status-critical';
            else if (avgTemp > 60) tempClass = 'status-warning';

            document.getElementById('avg-temperature').innerHTML =
                `<span class="${tempClass}">${avgTemp}°C</span>`;

            // Recent Events
            document.getElementById('recent-events').innerHTML =
                `<span class="status-info">${data.kpis.recent_events}</span>`;
        }
    }

    updateMachineGrid(machines) {
        const grid = document.getElementById('machine-grid');
        grid.innerHTML = '';

        if (!machines || Object.keys(machines).length === 0) {
            grid.innerHTML = '<div class="no-data-message">📊 No machine data available</div>';
            return;
        }

        Object.entries(machines).forEach(([machineName, machineData]) => {
            const temp = machineData.temperature || 0;
            const power = machineData.power || 0;
            const lastUpdate = machineData.last_update ?
                new Date(machineData.last_update).toLocaleTimeString() : 'Never';

            // Determine status based on data
            let statusClass = 'offline';
            let statusText = '⚫ OFFLINE';

            if (machineData.status === 'active') {
                if (temp > 85) {
                    statusClass = 'critical';
                    statusText = '🔴 CRITICAL';
                } else if (temp > 70) {
                    statusClass = 'warning';
                    statusText = '🟡 WARNING';
                } else {
                    statusClass = 'online';
                    statusText = '🟢 ACTIVE';
                }
            } else if (machineData.status === 'idle') {
                statusClass = 'warning';
                statusText = '🟡 IDLE';
            }

            const machineCard = document.createElement('div');
            machineCard.className = `machine-card ${statusClass} fade-in`;
            machineCard.onclick = () => this.showMachineDetails(machineName);

            machineCard.innerHTML = `
                <div class="machine-header">
                    <div class="machine-name">${machineName}</div>
                </div>
                <div class="machine-metrics">
                    <div class="metric">
                        <div class="metric-value ${temp > 80 ? 'status-critical' : temp > 60 ? 'status-warning' : 'status-online'}">${temp.toFixed(1)}°C</div>
                        <div class="metric-label">Temperature</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value status-info">${power.toFixed(2)} kW</div>
                        <div class="metric-label">Power</div>
                    </div>
                </div>
                <div class="machine-status">${statusText}</div>
                <div style="margin-top: 10px; font-size: 0.8rem; color: #a0aec0;">
                    Updated: ${lastUpdate}
                </div>
            `;

            grid.appendChild(machineCard);
        });
    }

    updateEventsTable(events) {
        const tbody = document.getElementById('events-table');
        tbody.innerHTML = '';

        if (!events || events.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #a0aec0;">No recent events</td></tr>';
            return;
        }

        events.slice(0, 10).forEach(event => {
            const time = new Date(event.time).toLocaleString();
            const eventBadge = `<span class="event-badge event-${event.event}">${event.event}</span>`;
            const details = this.formatEventDetails(event);

            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${time}</td>
                <td>${event.entity}</td>
                <td>${eventBadge}</td>
                <td>${event.piece_id || '-'}</td>
                <td>${details}</td>
            `;
            tbody.appendChild(row);
        });
    }

    formatEventDetails(event) {
        const details = [];
        if (event.from && event.to) {
            details.push(`${event.from} → ${event.to}`);
        }
        if (event.tool) {
            details.push(`Tool: ${event.tool}`);
        }
        return details.join(', ') || '-';
    }

    async loadChartData() {
        try {
            const machines = ['Saw1', 'Milling1', 'Milling2', 'Lathe1'];
            const chartData = {};

            for (const machine of machines) {
                const response = await fetch(`${this.apiBaseUrl}/api/sensors/${machine}?hours=1`);
                if (response.ok) {
                    const data = await response.json();
                    chartData[machine] = data.data;
                }
            }

            this.updateCharts(null, chartData);
        } catch (error) {
            console.error('Error loading chart data:', error);
        }
    }

    updateCharts(liveData, historicalData) {
        // Update charts with new data
        if (window.chartManager) {
            if (historicalData) {
                window.chartManager.updateWithHistoricalData(historicalData);
            }
            if (liveData) {
                window.chartManager.updateWithLiveData(liveData);
            }
        }
    }

    showMachineDetails(machineName) {
        console.log(`Showing details for ${machineName}`);
        this.loadMachineDetails(machineName);
    }

    async loadMachineDetails(machineName) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/api/sensors/${machineName}?hours=24`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.showMachineModal(machineName, data.data);
        } catch (error) {
            console.error(`Error loading details for ${machineName}:`, error);
            this.showError(`Failed to load details for ${machineName}`);
        }
    }

    showMachineModal(machineName, sensorData) {
        // Create and show modal with machine details
        const modalHtml = `
            <div class="modal" id="machineModal" onclick="this.style.display='none'">
                <div class="modal-content" onclick="event.stopPropagation()">
                    <span class="modal-close" onclick="document.getElementById('machineModal').style.display='none'">&times;</span>
                    <h2 style="margin-bottom: 20px; color: #00d4ff;">${machineName} Details</h2>
                    <div style="max-height: 400px; overflow-y: auto;">
                        <p style="margin-bottom: 15px;">Latest sensor readings for ${machineName}:</p>
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Temperature</th>
                                    <th>Power</th>
                                    <th>Additional Metrics</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${this.generateSensorTable(sensorData.slice(-20))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal
        const existingModal = document.getElementById('machineModal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add new modal
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // Show modal
        document.getElementById('machineModal').style.display = 'block';
    }

    generateSensorTable(sensorData) {
        if (!sensorData || sensorData.length === 0) {
            return '<tr><td colspan="4" style="text-align: center; color: #a0aec0;">No sensor data available</td></tr>';
        }

        return sensorData.map(reading => {
            const time = new Date(reading.time).toLocaleTimeString();
            const temp = reading.temperature || 'N/A';
            const power = reading.power || 'N/A';
            const additionalMetrics = this.getAdditionalMetrics(reading);

            return `
                <tr>
                    <td>${time}</td>
                    <td style="color: ${temp > 80 ? '#f56565' : temp > 60 ? '#ed8936' : '#48bb78'}">${temp}${temp !== 'N/A' ? '°C' : ''}</td>
                    <td style="color: #4299e1">${power}${power !== 'N/A' ? ' kW' : ''}</td>
                    <td style="color: #a0aec0; font-size: 0.9rem;">${additionalMetrics}</td>
                </tr>
            `;
        }).join('');
    }

    getAdditionalMetrics(reading) {
        const metrics = [];
        if (reading.blade_speed) metrics.push(`Blade: ${reading.blade_speed} RPM`);
        if (reading.rpm_spindle) metrics.push(`Spindle: ${reading.rpm_spindle} RPM`);
        if (reading.feed_rate) metrics.push(`Feed: ${reading.feed_rate}`);
        if (reading.vibration_level) metrics.push(`Vibration: ${reading.vibration_level}`);
        if (reading.material_feed) metrics.push(`Material: ${reading.material_feed}`);
        if (reading.cut_depth) metrics.push(`Depth: ${reading.cut_depth}`);

        return metrics.join(', ') || 'N/A';
    }

    updateLastUpdateTime() {
        const now = new Date();
        document.getElementById('last-update').textContent = now.toLocaleTimeString();
    }

    setupDataRefresh() {
        // Fallback refresh every 30 seconds if WebSocket fails
        setInterval(() => {
            if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
                console.log('📡 Refreshing data (WebSocket offline)');
                this.loadInitialData();
            }
        }, 30000);
    }

    showError(message) {
        console.error(message);

        // Create error notification
        const errorContainer = document.getElementById('errorContainer');
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message fade-in';
        errorDiv.innerHTML = `
            <strong>Error:</strong> ${message}
            <button onclick="this.parentElement.remove()" style="float: right; background: none; border: none; color: #f56565; cursor: pointer; font-size: 1.2rem;">&times;</button>
        `;

        errorContainer.appendChild(errorDiv);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.remove();
            }
        }, 5000);
    }

    clearErrors() {
        const errorContainer = document.getElementById('errorContainer');
        errorContainer.innerHTML = '';
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Clear any loading states
    document.querySelectorAll('.loading').forEach(el => {
        el.style.display = 'none';
    });

    // Initialize dashboard
    window.dashboard = new DashboardApp();
});

// Handle page visibility change to pause/resume updates
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        console.log('📱 Page hidden, maintaining connection');
    } else {
        console.log('📱 Page visible, refreshing data');
        if (window.dashboard) {
            window.dashboard.loadInitialData();
        }
    }
});

// Handle window resize for responsive design
window.addEventListener('resize', () => {
    if (window.chartManager) {
        setTimeout(() => {
            if (window.chartManager.temperatureChart) {
                window.chartManager.temperatureChart.resize();
            }
            if (window.chartManager.powerChart) {
                window.chartManager.powerChart.resize();
            }
        }, 100);
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Press 'R' to refresh
    if (e.key === 'r' || e.key === 'R') {
        if (!e.ctrlKey && !e.metaKey) { // Avoid interfering with browser refresh
            e.preventDefault();
            if (window.dashboard) {
                window.dashboard.loadInitialData();
                console.log('🔄 Manual refresh triggered');
            }
        }
    }

    // Press 'Escape' to close modal
    if (e.key === 'Escape') {
        const modal = document.getElementById('machineModal');
        if (modal) {
            modal.style.display = 'none';
        }
    }
});