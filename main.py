from datetime import datetime, timedelta
from statistics import mean, stdev
from typing import List

import firebase_admin
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from firebase_admin import credentials, db
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

# Initialize Firebase
cred = credentials.Certificate('firebaseSecret.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://realtimetemp-4fb14-default-rtdb.asia-southeast1.firebasedatabase.app'
})

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],  # Expose all headers
)


# Data Models
class SensorReading(BaseModel):
    temperature: float
    humidity: float


class ReadingResponse(BaseModel):
    temperature: float
    humidity: float
    timestamp: str


# Routes
@app.get("/")
async def root():
    return {"message": "Temperature & Humidity Tracking API", "version": "1.0"}

@app.head("/")
async def root_head():
    return { "message": "Temperature & Humidity Tracking API", "version": "1.0"}

@app.post("/reading")
async def add_reading(reading: SensorReading):
    """Add a new temperature and humidity reading"""
    try:
        if not (-50 <= reading.temperature <= 150):
            raise HTTPException(status_code=400, detail="Temperature out of valid range")
        if not (0 <= reading.humidity <= 100):
            raise HTTPException(status_code=400, detail="Humidity must be between 0 and 100")

        ref = db.reference('readings')
        new_reading = {
            'temperature': reading.temperature,
            'humidity': reading.humidity,
            'timestamp': datetime.now().isoformat()
        }
        ref.push(new_reading)
        return {
            "status": "success",
            "message": "Reading recorded",
            "data": new_reading
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/readings")
async def get_readings(hours: int = 24) -> List[ReadingResponse]:
    """Get all temperature and humidity readings"""
    try:
        ref = db.reference('readings')
        readings = ref.get()

        if not readings:
            return []

        cutoff_time = datetime.now() - timedelta(hours=hours)
        filtered_readings = []

        for key, reading in readings.items():
            timestamp = datetime.fromisoformat(reading['timestamp'])
            if timestamp > cutoff_time:
                filtered_readings.append({
                    "temperature": reading['temperature'],
                    "humidity": reading['humidity'],
                    "timestamp": reading['timestamp']
                })

        return sorted(filtered_readings, key=lambda x: x['timestamp'])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analysis")
async def get_analysis(hours: int = 24):
    """Get trend analysis and statistics"""
    try:
        ref = db.reference('readings')
        readings = ref.get()

        if not readings:
            raise HTTPException(status_code=404, detail="No readings found")

        cutoff_time = datetime.now() - timedelta(hours=hours)
        temps = []
        humidities = []
        timestamps = []

        for key, reading in readings.items():
            timestamp = datetime.fromisoformat(reading['timestamp'])
            if timestamp > cutoff_time:
                temps.append(reading['temperature'])
                humidities.append(reading['humidity'])
                timestamps.append(timestamp)

        if not temps:
            raise HTTPException(status_code=404, detail="No recent readings found")

        # Calculate statistics
        avg_temp = mean(temps)
        avg_humidity = mean(humidities)
        max_temp = max(temps)
        min_temp = min(temps)
        max_humidity = max(humidities)
        min_humidity = min(humidities)

        # Trend detection
        sorted_data = sorted(zip(timestamps, temps, humidities), key=lambda x: x[0])

        if len(sorted_data) > 1:
            first_half_temp = [t[1] for t in sorted_data[:len(sorted_data) // 2]]
            second_half_temp = [t[1] for t in sorted_data[len(sorted_data) // 2:]]
            temp_trend = "↑ Rising" if mean(second_half_temp) > mean(first_half_temp) else "↓ Falling"

            first_half_hum = [t[2] for t in sorted_data[:len(sorted_data) // 2]]
            second_half_hum = [t[2] for t in sorted_data[len(sorted_data) // 2:]]
            humidity_trend = "↑ Rising" if mean(second_half_hum) > mean(first_half_hum) else "↓ Falling"
        else:
            temp_trend = "→ Stable"
            humidity_trend = "→ Stable"

        # Comfort analysis
        comfort_score = 0
        temp_comment = ""
        humidity_comment = ""

        if 18 <= avg_temp <= 24:
            comfort_score += 50
            temp_comment = "Optimal temperature"
        elif 15 <= avg_temp <= 30:
            comfort_score += 25
            temp_comment = "Acceptable temperature"
        else:
            temp_comment = "Outside comfort zone"

        if 40 <= avg_humidity <= 60:
            comfort_score += 50
            humidity_comment = "Optimal humidity"
        elif 30 <= avg_humidity <= 70:
            comfort_score += 25
            humidity_comment = "Acceptable humidity"
        else:
            humidity_comment = "Outside comfort zone"

        if comfort_score >= 80:
            comfort_level = "Excellent"
        elif comfort_score >= 60:
            comfort_level = "Good"
        elif comfort_score >= 40:
            comfort_level = "Fair"
        else:
            comfort_level = "Poor"

        # Anomaly detection
        anomalies = []
        if len(temps) > 2:
            temp_std = stdev(temps)
            humidity_std = stdev(humidities)

            for i, (ts, temp, hum) in enumerate(sorted_data):
                if abs(temp - avg_temp) > 2 * temp_std or abs(hum - avg_humidity) > 2 * humidity_std:
                    anomalies.append({
                        'temperature': temp,
                        'humidity': hum,
                        'timestamp': ts.isoformat(),
                        'reason': 'Temperature spike' if abs(temp - avg_temp) > 2 * temp_std else 'Humidity spike'
                    })

        return {
            "period_hours": hours,
            "readings_count": len(temps),
            "temperature": {
                "average": round(avg_temp, 2),
                "max": round(max_temp, 2),
                "min": round(min_temp, 2),
                "trend": temp_trend
            },
            "humidity": {
                "average": round(avg_humidity, 2),
                "max": round(max_humidity, 2),
                "min": round(min_humidity, 2),
                "trend": humidity_trend
            },
            "comfort": {
                "level": comfort_level,
                "score": comfort_score,
                "temperature_comment": temp_comment,
                "humidity_comment": humidity_comment
            },
            "anomalies": anomalies[:5]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """Interactive dashboard with graphs and trend analysis"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Temperature & Humidity Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
            }
            h1 {
                color: white;
                text-align: center;
                margin-bottom: 30px;
                font-size: 2.5em;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            .controls {
                display: flex;
                gap: 10px;
                margin-bottom: 30px;
                justify-content: center;
                flex-wrap: wrap;
            }
            input, button, select {
                padding: 12px 20px;
                font-size: 1em;
                border: none;
                border-radius: 8px;
                background: white;
                color: #333;
                cursor: pointer;
                transition: all 0.3s;
            }
            input:focus, select:focus {
                outline: none;
                box-shadow: 0 0 0 3px rgba(255,255,255,0.3);
            }
            button {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                font-weight: bold;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .card {
                background: white;
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 8px 16px rgba(0,0,0,0.1);
                transition: transform 0.3s;
            }
            .card:hover {
                transform: translateY(-5px);
                box-shadow: 0 12px 20px rgba(0,0,0,0.15);
            }
            .stat {
                text-align: center;
            }
            .stat-label {
                color: #666;
                font-size: 0.9em;
                margin-bottom: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .stat-value {
                font-size: 2.5em;
                font-weight: bold;
                color: #667eea;
                margin-bottom: 5px;
            }
            .stat-unit {
                color: #999;
                font-size: 1em;
            }
            .trend {
                font-size: 1.2em;
                margin-top: 10px;
                padding: 10px;
                background: #f0f0f0;
                border-radius: 6px;
            }
            .comfort-excellent { background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%); color: white; }
            .comfort-good { background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); color: white; }
            .comfort-fair { background: linear-gradient(135deg, #ffa751 0%, #ffe259 100%); color: white; }
            .comfort-poor { background: linear-gradient(135deg, #ff6a88 0%, #ff9a44 100%); color: white; }

            .charts {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .chart-container {
                background: white;
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 8px 16px rgba(0,0,0,0.1);
                position: relative;
                height: 400px;
            }
            .anomalies {
                background: white;
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 8px 16px rgba(0,0,0,0.1);
            }
            .anomaly-item {
                padding: 15px;
                background: #fff3cd;
                border-left: 4px solid #ffc107;
                margin-bottom: 10px;
                border-radius: 4px;
            }
            .no-data {
                text-align: center;
                color: #999;
                padding: 40px;
                font-size: 1.1em;
            }
            .loading {
                text-align: center;
                color: white;
                font-size: 1.2em;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Climate Monitor</h1>

            <div class="controls">
                <select id="hoursSelect">
                    <option value="1">Last 1 Hour</option>
                    <option value="6">Last 6 Hours</option>
                    <option value="24" selected>Last 24 Hours</option>
                    <option value="168">Last 7 Days</option>
                </select>
                <button onclick="loadData()">🔄 Refresh</button>
                <button onclick="addReading()">➕ Add Reading</button>
            </div>

            <div id="loadingDiv" class="loading" style="display:none;">Loading data...</div>

            <div id="statsDiv" class="grid"></div>
            <div id="chartsDiv" class="charts"></div>
            <div id="anomaliesDiv"></div>
        </div>

        <script>
            let tempChart, humidityChart;

            async function loadData() {
                document.getElementById('loadingDiv').style.display = 'block';
                const hours = document.getElementById('hoursSelect').value;

                try {
                    const [readings, analysis] = await Promise.all([
                        fetch(`/readings?hours=${hours}`).then(r => r.json()),
                        fetch(`/analysis?hours=${hours}`).then(r => r.json())
                    ]);

                    displayStats(analysis);
                    displayCharts(readings, analysis);
                    displayAnomalies(analysis);
                } catch (error) {
                    alert('Error loading data: ' + error);
                } finally {
                    document.getElementById('loadingDiv').style.display = 'none';
                }
            }

            function displayStats(analysis) {
                const comfortClass = 'comfort-' + analysis.comfort.level.toLowerCase();
                const html = `
                    <div class="card stat">
                        <div class="stat-label">🌡️ Temperature</div>
                        <div class="stat-value">${analysis.temperature.average}°C</div>
                        <div class="stat-unit">Avg (${analysis.temperature.min}° - ${analysis.temperature.max}°)</div>
                        <div class="trend">${analysis.temperature.trend}</div>
                    </div>
                    <div class="card stat">
                        <div class="stat-label">💧 Humidity</div>
                        <div class="stat-value">${analysis.humidity.average}%</div>
                        <div class="stat-unit">Avg (${analysis.humidity.min}% - ${analysis.humidity.max}%)</div>
                        <div class="trend">${analysis.humidity.trend}</div>
                    </div>
                    <div class="card stat ${comfortClass}">
                        <div class="stat-label">✨ Comfort Level</div>
                        <div class="stat-value">${analysis.comfort.level}</div>
                        <div class="stat-unit">Score: ${analysis.comfort.score}/100</div>
                        <div style="font-size: 0.8em; margin-top: 10px;">
                            <div>${analysis.comfort.temperature_comment}</div>
                            <div>${analysis.comfort.humidity_comment}</div>
                        </div>
                    </div>
                `;
                document.getElementById('statsDiv').innerHTML = html;
            }

            function displayCharts(readings, analysis) {
                if (readings.length === 0) {
                    document.getElementById('chartsDiv').innerHTML = '<div class="no-data">No data available</div>';
                    return;
                }

                const timestamps = readings.map(r => new Date(r.timestamp).toLocaleTimeString());
                const temps = readings.map(r => r.temperature);
                const humidities = readings.map(r => r.humidity);

                const html = `
                    <div class="chart-container">
                        <canvas id="tempChart"></canvas>
                    </div>
                    <div class="chart-container">
                        <canvas id="humidityChart"></canvas>
                    </div>
                `;
                document.getElementById('chartsDiv').innerHTML = html;

                setTimeout(() => {
                    const tempCtx = document.getElementById('tempChart').getContext('2d');
                    tempChart = new Chart(tempCtx, {
                        type: 'line',
                        data: {
                            labels: timestamps,
                            datasets: [{
                                label: 'Temperature (°C)',
                                data: temps,
                                borderColor: '#ff6b6b',
                                backgroundColor: 'rgba(255, 107, 107, 0.1)',
                                borderWidth: 2,
                                fill: true,
                                tension: 0.4,
                                pointRadius: 4,
                                pointBackgroundColor: '#ff6b6b'
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: true, position: 'top' } },
                            scales: { y: { beginAtZero: false } }
                        }
                    });

                    const humidityCtx = document.getElementById('humidityChart').getContext('2d');
                    humidityChart = new Chart(humidityCtx, {
                        type: 'line',
                        data: {
                            labels: timestamps,
                            datasets: [{
                                label: 'Humidity (%)',
                                data: humidities,
                                borderColor: '#4ecdc4',
                                backgroundColor: 'rgba(78, 205, 196, 0.1)',
                                borderWidth: 2,
                                fill: true,
                                tension: 0.4,
                                pointRadius: 4,
                                pointBackgroundColor: '#4ecdc4'
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: true, position: 'top' } },
                            scales: { y: { min: 0, max: 100 } }
                        }
                    });
                }, 0);
            }

            function displayAnomalies(analysis) {
                if (analysis.anomalies.length === 0) {
                    document.getElementById('anomaliesDiv').innerHTML = '';
                    return;
                }

                let html = '<div class="anomalies"><h2>⚠️ Detected Anomalies</h2>';
                analysis.anomalies.forEach(a => {
                    const time = new Date(a.timestamp).toLocaleString();
                    html += `<div class="anomaly-item"><strong>${a.reason}</strong> - ${a.temperature}°C, ${a.humidity}% at ${time}</div>`;
                });
                html += '</div>';
                document.getElementById('anomaliesDiv').innerHTML = html;
            }

            async function addReading() {
                const temp = prompt('Enter temperature (°C):');
                if (temp === null) return;
                const humidity = prompt('Enter humidity (%):');
                if (humidity === null) return;

                try {
                    const response = await fetch('/reading', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            temperature: parseFloat(temp),
                            humidity: parseFloat(humidity)
                        })
                    });

                    if (response.ok) {
                        alert('Reading added successfully!');
                        loadData();
                    } else {
                        alert('Error adding reading');
                    }
                } catch (error) {
                    alert('Error: ' + error);
                }
            }

            loadData();
            setInterval(loadData, 60000);
        </script>
    </body>
    </html>
    """


@app.delete("/readings")
async def clear_all_readings():
    """Clear all readings"""
    try:
        ref = db.reference('readings')
        ref.delete()
        return {"status": "success", "message": "All readings deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))