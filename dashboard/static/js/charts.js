// Charts Management for Dashboard

class ChartManager {
    constructor() {
        this.temperatureChart = null;
        this.powerChart = null;
        this.chartColors = {
            'Saw1': '#ff6384',
            'Milling1': '#36a2eb',
            'Milling2': '#ffce56',
            'Lathe1': '#4bc0c0'
        };

        this.init();
    }

    init() {
        console.log('📊 Initializing charts...');
        this.createTemperatureChart();
        this.createPowerChart();
        console.log('✅ Charts initialized');
    }

    createTemperatureChart() {
        const ctx = document.getElementById('temperatureChart');
        if (!ctx) return;

        this.temperatureChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Saw1',
                        data: [],
                        borderColor: this.chartColors['Saw1'],
                        backgroundColor: this.chartColors['Saw1'] + '20',
                        tension: 0.4,
                        fill: false
                    },
                    {
                        label: 'Milling1',
                        data: [],
                        borderColor: this.chartColors['Milling1'],
                        backgroundColor: this.chartColors['Milling1'] + '20',
                        tension: 0.4,
                        fill: false
                    },
                    {
                        label: 'Milling2',
                        data: [],
                        borderColor: this.chartColors['Milling2'],
                        backgroundColor: this.chartColors['Milling2'] + '20',
                        tension: 0.4,
                        fill: false
                    },
                    {
                        label: 'Lathe1',
                        data: [],
                        borderColor: this.chartColors['Lathe1'],
                        backgroundColor: this.chartColors['Lathe1'] + '20',
                        tension: 0.4,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: false
                    },
                    legend: {
                        labels: {
                            color: '#ffffff'
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: '#ffffff',
                            maxTicksLimit: 10
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    },
                    y: {
                        beginAtZero: false,
                        ticks: {
                            color: '#ffffff',
                            callback: function (value) {
                                return value + '°C';
                            }
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                elements: {
                    point: {
                        radius: 3,
                        hoverRadius: 6
                    }
                }
            }
        });
    }

    createPowerChart() {
        const ctx = document.getElementById('powerChart');
        if (!ctx) return;

        this.powerChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Saw1',
                        data: [],
                        borderColor: this.chartColors['Saw1'],
                        backgroundColor: this.chartColors['Saw1'] + '20',
                        tension: 0.4,
                        fill: false
                    },
                    {
                        label: 'Milling1',
                        data: [],
                        borderColor: this.chartColors['Milling1'],
                        backgroundColor: this.chartColors['Milling1'] + '20',
                        tension: 0.4,
                        fill: false
                    },
                    {
                        label: 'Milling2',
                        data: [],
                        borderColor: this.chartColors['Milling2'],
                        backgroundColor: this.chartColors['Milling2'] + '20',
                        tension: 0.4,
                        fill: false
                    },
                    {
                        label: 'Lathe1',
                        data: [],
                        borderColor: this.chartColors['Lathe1'],
                        backgroundColor: this.chartColors['Lathe1'] + '20',
                        tension: 0.4,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: false
                    },
                    legend: {
                        labels: {
                            color: '#ffffff'
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: '#ffffff',
                            maxTicksLimit: 10
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: '#ffffff',
                            callback: function (value) {
                                return value + ' kW';
                            }
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                elements: {
                    point: {
                        radius: 3,
                        hoverRadius: 6
                    }
                }
            }
        });
    }

    updateWithHistoricalData(chartData) {
        console.log('📊 Updating charts with historical data');

        // Process data for temperature chart
        const tempData = this.processHistoricalData(chartData, 'temperature');
        this.updateChart(this.temperatureChart, tempData);

        // Process data for power chart
        const powerData = this.processHistoricalData(chartData, 'power');
        this.updateChart(this.powerChart, powerData);
    }

    updateWithLiveData(machines) {
        console.log('📊 Updating charts with live data');

        const currentTime = new Date().toLocaleTimeString();

        // Update temperature chart
        if (this.temperatureChart) {
            this.addDataPoint(this.temperatureChart, currentTime, machines, 'temperature');
        }

        // Update power chart
        if (this.powerChart) {
            this.addDataPoint(this.powerChart, currentTime, machines, 'power');
        }
    }

    processHistoricalData(chartData, metric) {
        const processedData = {
            labels: [],
            datasets: {}
        };

        // Initialize datasets for each machine
        Object.keys(this.chartColors).forEach(machine => {
            processedData.datasets[machine] = [];
        });

        // Get all unique timestamps
        const allTimestamps = new Set();
        Object.values(chartData).forEach(machineData => {
            machineData.forEach(reading => {
                if (reading[metric] !== null && reading[metric] !== undefined) {
                    allTimestamps.add(reading.time);
                }
            });
        });

        // Sort timestamps
        const sortedTimestamps = Array.from(allTimestamps).sort();

        // Take last 50 points to avoid overcrowding
        const recentTimestamps = sortedTimestamps.slice(-50);

        processedData.labels = recentTimestamps.map(ts =>
            new Date(ts).toLocaleTimeString()
        );

        // Fill data for each machine
        Object.entries(chartData).forEach(([machine, readings]) => {
            if (processedData.datasets[machine]) {
                processedData.datasets[machine] = recentTimestamps.map(timestamp => {
                    const reading = readings.find(r => r.time === timestamp);
                    return reading ? reading[metric] || null : null;
                });
            }
        });

        return processedData;
    }

    updateChart(chart, data) {
        if (!chart || !data) return;

        chart.data.labels = data.labels;

        chart.data.datasets.forEach((dataset, index) => {
            const machineName = dataset.label;
            if (data.datasets[machineName]) {
                dataset.data = data.datasets[machineName];
            }
        });

        chart.update('none'); // Update without animation for better performance
    }

    addDataPoint(chart, time, machines, metric) {
        if (!chart) return;

        // Add new time label
        chart.data.labels.push(time);

        // Add data for each machine
        chart.data.datasets.forEach(dataset => {
            const machineName = dataset.label;
            const machineData = machines[machineName];
            const value = machineData ? machineData[metric] || null : null;
            dataset.data.push(value);
        });

        // Keep only last 20 points for real-time view
        const maxPoints = 20;
        if (chart.data.labels.length > maxPoints) {
            chart.data.labels.shift();
            chart.data.datasets.forEach(dataset => {
                dataset.data.shift();
            });
        }

        chart.update('none');
    }

    setChartHeight(height = '300px') {
        const charts = [this.temperatureChart, this.powerChart];
        charts.forEach(chart => {
            if (chart && chart.canvas) {
                chart.canvas.parentNode.style.height = height;
                chart.resize();
            }
        });
    }

    destroyCharts() {
        if (this.temperatureChart) {
            this.temperatureChart.destroy();
            this.temperatureChart = null;
        }
        if (this.powerChart) {
            this.powerChart.destroy();
            this.powerChart = null;
        }
    }

    refreshCharts() {
        console.log('🔄 Refreshing charts...');
        this.destroyCharts();
        this.init();
    }

    // Create additional chart for specific machine details
    createMachineDetailChart(elementId, machineData, metrics) {
        const ctx = document.getElementById(elementId);
        if (!ctx) return null;

        const datasets = metrics.map((metric, index) => ({
            label: metric.charAt(0).toUpperCase() + metric.slice(1),
            data: machineData.map(reading => reading[metric] || null),
            borderColor: this.getMetricColor(metric, index),
            backgroundColor: this.getMetricColor(metric, index) + '20',
            tension: 0.4,
            fill: false
        }));

        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: machineData.map(reading =>
                    new Date(reading.time).toLocaleTimeString()
                ),
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: '#ffffff'
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#ffffff' },
                        grid: { color: 'rgba(255, 255, 255, 0.1)' }
                    },
                    y: {
                        ticks: { color: '#ffffff' },
                        grid: { color: 'rgba(255, 255, 255, 0.1)' }
                    }
                }
            }
        });
    }

    getMetricColor(metric, index) {
        const colors = [
            '#ff6384', '#36a2eb', '#ffce56', '#4bc0c0',
            '#9966ff', '#ff9f40', '#ff6384', '#c9cbcf'
        ];
        return colors[index % colors.length];
    }
}

// Initialize chart manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.chartManager = new ChartManager();
});

// Handle window resize
window.addEventListener('resize', () => {
    if (window.chartManager) {
        setTimeout(() => {
            window.chartManager.setChartHeight();
        }, 100);
    }
});