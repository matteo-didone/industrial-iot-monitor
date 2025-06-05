import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryApi
import uvicorn
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
INFLUXDB_URL = f"{os.getenv('INFLUX_ADDRESS', 'http://localhost')}:{int(os.getenv('INFLUX_PORT', '8086'))}"
INFLUXDB_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUX_ORG")
INFLUXDB_BUCKET = os.getenv("INFLUX_BUCKET")

# FastAPI app
app = FastAPI(title="Industrial IoT Monitor Dashboard", version="1.0.0")

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")

# InfluxDB client
influxdb_client: InfluxDBClient = None
query_api: QueryApi = None

# WebSocket connections manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if self.active_connections:
            message_str = json.dumps(message)
            for connection in self.active_connections[:]:  # Copy to avoid issues during iteration
                try:
                    await connection.send_text(message_str)
                except Exception as e:
                    logger.error(f"Error sending WebSocket message: {e}")
                    self.disconnect(connection)

manager = ConnectionManager()

def init_influxdb():
    """Initialize InfluxDB connection"""
    global influxdb_client, query_api
    try:
        influxdb_client = InfluxDBClient(
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG
        )
        influxdb_client.ping()
        query_api = influxdb_client.query_api()
        logger.info("✅ InfluxDB connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to connect to InfluxDB: {e}")
        return False

def query_sensor_data(entity: str = None, hours: int = 1) -> List[Dict]:
    """Query latest sensor data from InfluxDB"""
    if not query_api:
        return []
    
    try:
        entity_filter = f'|> filter(fn: (r) => r["entity"] == "{entity}")' if entity else ''
        
        query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -{hours}h)
          |> filter(fn: (r) => r["_measurement"] == "sensor_data")
          {entity_filter}
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> sort(columns: ["_time"], desc: false)
        '''
        
        result = query_api.query(query)
        
        data = []
        for table in result:
            for record in table.records:
                data.append({
                    'time': record.get_time().isoformat(),
                    'entity': record.values.get('entity'),
                    'temperature': record.values.get('temperature'),
                    'power': record.values.get('power'),
                    'blade_speed': record.values.get('blade_speed'),
                    'rpm_spindle': record.values.get('rpm_spindle'),
                    'feed_rate': record.values.get('feed_rate'),
                    'vibration_level': record.values.get('vibration_level'),
                    'material_feed': record.values.get('material_feed'),
                    'cut_depth': record.values.get('cut_depth')
                })
        
        return data[-100:]  # Return last 100 points
    except Exception as e:
        logger.error(f"Error querying sensor data: {e}")
        return []

def query_tracking_events(hours: int = 24) -> List[Dict]:
    """Query tracking events from InfluxDB"""
    if not query_api:
        return []
    
    try:
        query = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -{hours}h)
          |> filter(fn: (r) => r["_measurement"] == "tracking_events")
          |> filter(fn: (r) => r["_field"] == "count")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 50)
        '''
        
        result = query_api.query(query)
        
        events = []
        for table in result:
            for record in table.records:
                events.append({
                    'time': record.get_time().isoformat(),
                    'entity': record.values.get('entity'),
                    'event': record.values.get('event'),
                    'piece_id': record.values.get('piece_id'),
                    'from': record.values.get('from'),
                    'to': record.values.get('to'),
                    'tool': record.values.get('tool')
                })
        
        return events
    except Exception as e:
        logger.error(f"Error querying tracking events: {e}")
        return []

def get_machine_status() -> Dict[str, Any]:
    """Get current status of all machines"""
    machines = ['Saw1', 'Milling1', 'Milling2', 'Lathe1']
    status = {}
    
    for machine in machines:
        recent_data = query_sensor_data(machine, hours=1)
        if recent_data:
            latest = recent_data[-1]
            status[machine] = {
                'status': 'active' if len(recent_data) > 5 else 'idle',
                'temperature': latest.get('temperature', 0),
                'power': latest.get('power', 0),
                'last_update': latest.get('time')
            }
        else:
            status[machine] = {
                'status': 'offline',
                'temperature': 0,
                'power': 0,
                'last_update': None
            }
    
    return status

async def broadcast_live_data():
    """Background task to broadcast live data to WebSocket clients"""
    while True:
        try:
            if manager.active_connections:
                # Get latest data
                machine_status = get_machine_status()
                recent_events = query_tracking_events(hours=1)
                
                # Broadcast to all connected clients
                await manager.broadcast({
                    'type': 'live_update',
                    'timestamp': datetime.now().isoformat(),
                    'machines': machine_status,
                    'recent_events': recent_events[:5]  # Last 5 events
                })
            
            await asyncio.sleep(5)  # Update every 5 seconds
        except Exception as e:
            logger.error(f"Error in broadcast_live_data: {e}")
            await asyncio.sleep(10)

# Routes
@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Main dashboard page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    influx_status = "connected" if influxdb_client else "disconnected"
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "influxdb": influx_status,
        "active_connections": len(manager.active_connections)
    }

@app.get("/api/machines")
async def get_machines():
    """Get list of all machines with current status"""
    return get_machine_status()

@app.get("/api/sensors/{machine}")
async def get_machine_sensors(machine: str, hours: int = 1):
    """Get sensor data for a specific machine"""
    data = query_sensor_data(machine, hours)
    return {"machine": machine, "data": data}

@app.get("/api/events")
async def get_events(hours: int = 24):
    """Get tracking events"""
    events = query_tracking_events(hours)
    return {"events": events}

@app.get("/api/overview")
async def get_overview():
    """Get dashboard overview data"""
    machines = get_machine_status()
    events = query_tracking_events(hours=1)
    
    # Calculate KPIs
    active_machines = sum(1 for m in machines.values() if m['status'] == 'active')
    total_power = sum(m.get('power', 0) for m in machines.values())
    avg_temp = sum(m.get('temperature', 0) for m in machines.values()) / len(machines) if machines else 0
    
    return {
        "kpis": {
            "active_machines": active_machines,
            "total_machines": len(machines),
            "total_power": round(total_power, 2),
            "avg_temperature": round(avg_temp, 1),
            "recent_events": len(events)
        },
        "machines": machines,
        "recent_events": events[:10]
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.on_event("startup")
async def startup_event():
    """Initialize connections and start background tasks"""
    logger.info("🚀 Starting Industrial IoT Dashboard...")
    
    # Initialize InfluxDB
    if not init_influxdb():
        logger.error("Failed to initialize InfluxDB connection")
        return
    
    # Start background task for live data broadcasting
    asyncio.create_task(broadcast_live_data())
    
    logger.info("✅ Dashboard started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown"""
    logger.info("🛑 Shutting down dashboard...")
    if influxdb_client:
        influxdb_client.close()

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8080, 
        reload=True,
        log_level="info"
    )