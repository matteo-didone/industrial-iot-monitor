import time
import random
import threading
import os
from datetime import datetime, timedelta
import numpy as np
import paho.mqtt.client as mqtt
import json

# Simulation parameters from environment
DATA_SEND_INTERVAL = 3  # seconds between payloads (simulated)
NOMINAL_CYCLE_MIN = 8   # average processing time (minutes) - reduced for more activity
SIGMA_CYCLE_MIN = 1.0   # standard deviation (minutes)

# Transfer times between stations (minutes)
DIST_MIN = {
    ("Saw1", "Milling1"): 1,
    ("Saw1", "Lathe1"): 2,
    ("Saw1", "Milling2"): 2,
    ("Milling1", "Lathe1"): 1,
    ("Milling2", "Lathe1"): 1,
}
DEFAULT_MOVE_MIN = 1

# Factory clock
simulation_current_time = datetime.now()

def get_transport_time(from_station: str, to_station: str) -> float:
    """Returns transport time (minutes) with ±20% jitter."""
    base = DIST_MIN.get(
        (from_station, to_station),
        DIST_MIN.get((to_station, from_station), DEFAULT_MOVE_MIN)
    )
    jitter = random.uniform(-0.2, 0.2) * base
    return max(0.5, base + jitter)

def get_cycle_time_minutes() -> float:
    """Returns a normally distributed cycle time (min), truncated at ≥1 min."""
    return max(1.0, np.random.normal(NOMINAL_CYCLE_MIN, SIGMA_CYCLE_MIN))

class MQTTClient:
    """Improved MQTT client with better connection handling"""
    def __init__(self, broker_address, broker_port):
        # Use the new API version
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.broker_address = broker_address
        self.broker_port = broker_port
        self.connected = False
        
        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        
        # Connect to broker
        try:
            print(f"🔌 Connecting to MQTT broker {broker_address}:{broker_port}...")
            self.client.connect(broker_address, broker_port, 60)
            self.client.loop_start()  # Start background loop
            
            # Wait for connection
            retry_count = 0
            while not self.connected and retry_count < 10:
                time.sleep(1)
                retry_count += 1
            
            if self.connected:
                print(f"✅ Connected to MQTT broker")
            else:
                raise ConnectionError("Failed to connect after 10 retries")
                
        except Exception as e:
            print(f"❌ Failed to connect to MQTT broker: {e}")
            raise

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            print("✅ MQTT connection established")
        else:
            print(f"❌ MQTT connection failed with code: {rc}")

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self.connected = False
        if rc != 0:
            print("⚠️  Unexpected MQTT disconnection")

    def publish(self, topic, payload):
        if self.connected:
            try:
                result = self.client.publish(topic, json.dumps(payload))
                if result.rc != mqtt.MQTT_ERR_SUCCESS:
                    print(f"⚠️  Failed to publish to {topic}")
                else:
                    print(f"📤 Published to {topic}: {payload.get('entity', 'unknown')}")
            except Exception as e:
                print(f"❌ Error publishing to {topic}: {e}")
        else:
            print("⚠️  Cannot publish: MQTT not connected")
    
    def disconnect(self):
        """Clean disconnection"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            print("👋 MQTT client disconnected")

class Piece:
    """Represents a workpiece with routing, material, and tooling requirements."""
    def __init__(self, piece_id: str, route: list[str], material: str, tools: dict[str, list[str]]) -> None:
        self.piece_id = piece_id
        self.route = route
        self.material = material
        self.tools = tools

class Machine:
    """Simulates a machine that processes pieces, publishes data over MQTT."""
    def __init__(self, name: str, mtype: str, mqtt_client: MQTTClient, time_multiplier: int = 1) -> None:
        self.name = name
        self.type = mtype
        self.mqtt = mqtt_client
        self.time_multiplier = time_multiplier

        self.busy = False
        self.state = "idle"
        self.lock = threading.Lock()

        # Thermal model
        self.ambient_temp = 20.0
        self.thermal_time_const = 30.0
        self.heat_coeff = 5e-4
        self.current_temp = self.ambient_temp

        # Tool wear tracking
        self.current_tool: str | None = None
        self.tool_wear: dict[str, float] = {}
        self.max_wear_penalty = 0.5
        self.vibration_wear_coeff = 0.2

        self._baseline: dict[str, float] | None = None

    def _generate_baseline(self) -> dict[str, float]:
        """Generates a random baseline for sensor parameters."""
        if self.type == "Milling":
            return {
                "rpm_spindle": random.uniform(2500, 3500),
                "feed_rate": random.uniform(250, 350),
                "temperature": random.uniform(35, 45),
                "vibration_level": random.uniform(1.0, 2.0),
            }
        if self.type == "Lathe":
            return {
                "rpm_spindle": random.uniform(1200, 2000),
                "cut_depth": random.uniform(1.0, 3.0),
                "temperature": random.uniform(30, 40),
            }
        if self.type == "Saw":
            return {
                "blade_speed": random.uniform(1600, 2000),
                "material_feed": random.uniform(0.8, 1.2),
                "temperature": random.uniform(25, 35),
            }
        return {}

    @staticmethod
    def _apply_jitter(base: float, spread: float) -> float:
        """Applies ±spread jitter to a base value."""
        return round(base + random.uniform(-spread, spread), 2)

    def simulate_variable_data(self, dt: float) -> dict[str, float]:
        """Simulates realistic sensor data and updates thermal & vibration model."""
        if self._baseline is None:
            self._baseline = self._generate_baseline()
        b = self._baseline

        # Compute power based on machine type
        if self.type == "Milling":
            rpm = self._apply_jitter(b["rpm_spindle"], 100)
            feed = self._apply_jitter(b["feed_rate"], 10)
            power = rpm * feed * 1e-4
        elif self.type == "Lathe":
            rpm = self._apply_jitter(b["rpm_spindle"], 80)
            cut = self._apply_jitter(b["cut_depth"], 0.05)
            power = rpm * cut * 1e-3
        elif self.type == "Saw":
            speed = self._apply_jitter(b["blade_speed"], 90)
            feed = self._apply_jitter(b["material_feed"], 0.04)
            power = speed * feed * 5e-4
        else:
            return {}

        # First-order thermal model
        dT = (power * self.heat_coeff - (self.current_temp - self.ambient_temp) / self.thermal_time_const) * dt
        self.current_temp += dT + random.uniform(-0.2, 0.2)

        # Vibration including wear
        base_vib = round(0.1 * power + random.uniform(0, 0.1), 2)
        wear = self.tool_wear.get(self.current_tool, 0.0)
        vibration = round(base_vib * (1 + wear * self.vibration_wear_coeff), 2)

        data = {"temperature": round(self.current_temp, 2), "power": round(power, 2)}
        if self.type == "Milling":
            data.update({"rpm_spindle": rpm, "feed_rate": feed, "vibration_level": vibration})
        elif self.type == "Lathe":
            data.update({"rpm_spindle": rpm, "cut_depth": cut})
        elif self.type == "Saw":
            data.update({"blade_speed": speed, "material_feed": feed})
        return data

    def is_available(self) -> bool:
        """Indicates if machine is free to process new work."""
        return not self.busy

    def _publish_event(self, topic: str, payload: dict) -> None:
        """Helper to publish MQTT messages."""
        self.mqtt.publish(topic, payload)

    def _run_simulation(self, duration_s: float) -> None:
        """Runs sensor data simulation over the specified duration."""
        global simulation_current_time
        steps = int(duration_s / DATA_SEND_INTERVAL)
        print(f"  📊 Running {steps} sensor readings for {self.name}...")
        
        for step in range(steps):
            try:
                data = self.simulate_variable_data(DATA_SEND_INTERVAL)
                payload = {"entity": self.name, "data": data, "timestamp": simulation_current_time.isoformat()}
                self._publish_event(f"/plant/data/{self.name}", payload)

                simulation_current_time += timedelta(seconds=DATA_SEND_INTERVAL)
                time.sleep(DATA_SEND_INTERVAL / self.time_multiplier)
            except Exception as e:
                print(f"❌ Error in simulation step: {e}")
                break

    def setup_tool(self, tool: str, start_time: datetime) -> None:
        """Performs tool setup, including wear incrementation."""
        global simulation_current_time
        setup_min = random.uniform(2, 4)  # Reduced setup time
        duration_s = setup_min * 60

        self.state = "setup"
        print(f"  🔧 {self.name}: Setting up tool {tool}...")
        
        self._publish_event(f"/plant/tracking/{self.name}", {
            "entity": self.name,
            "event": "setup_start",
            "data": {"tool": tool},
            "timestamp": start_time.isoformat(),
        })

        simulation_current_time += timedelta(minutes=setup_min)
        time.sleep(duration_s / self.time_multiplier)

        # Update tool and wear
        self.current_tool = tool
        self.tool_wear[tool] = min(1.0, self.tool_wear.get(tool, 0.0) + 0.05)

        self._publish_event(f"/plant/tracking/{self.name}", {
            "entity": self.name,
            "event": "setup_end",
            "data": {"tool": tool},
            "timestamp": simulation_current_time.isoformat(),
        })
        self.state = "idle"

    def process(self, piece_id: str, duration_s: float, start_time: datetime, tools_map: dict) -> None:
        """Processes a piece in time slices per required tools."""
        tool_list = tools_map.get(self.type, [None])
        adjusted = duration_s * random.uniform(0.8, 1.2)  # More variation
        slice_s = adjusted / len(tool_list)

        print(f"  ⚙️  {self.name}: Processing {piece_id} with tools {tool_list}")

        for tool in tool_list:
            if self.type in ("Milling", "Lathe") and tool != self.current_tool:
                self.setup_tool(tool, start_time)
                start_time = simulation_current_time

            self.state = "processing"
            self.busy = True
            self._publish_event(f"/plant/tracking/{self.name}", {
                "entity": self.name,
                "event": "processing_start",
                "data": {"piece_id": piece_id, "tool": tool},
                "timestamp": start_time.isoformat(),
            })

            self._run_simulation(slice_s)

            end_time = simulation_current_time
            self._publish_event(f"/plant/tracking/{self.name}", {
                "entity": self.name,
                "event": "processing_end",
                "data": {"piece_id": piece_id, "tool": tool},
                "timestamp": end_time.isoformat(),
            })

            self.state = "idle"
            self.busy = False
            start_time = end_time

def publish_tracking_event(mqtt_client: MQTTClient, entity: str, event: str, data: dict, timestamp: str) -> None:
    """Publishes a generic tracking event."""
    mqtt_client.publish(f"/plant/tracking/{entity}", {
        "entity": entity, 
        "event": event, 
        "data": data, 
        "timestamp": timestamp
    })
    
if __name__ == "__main__":
    import signal
    import sys
    
    # Configuration from environment variables
    BROKER_ADDRESS = os.getenv('MQTT_BROKER', 'localhost')
    BROKER_PORT = int(os.getenv('MQTT_PORT', '1883'))
    TIME_MULTIPLIER = float(os.getenv('TIME_MULTIPLIER', '8.0'))  # Faster simulation
    PIECE_COUNT = int(os.getenv('PIECE_COUNT', '10'))  # More pieces

    # Statistics
    stats = {'pieces_processed': 0, 'messages_sent': 0, 'start_time': datetime.now()}
    mqtt_client = None
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully"""
        print(f"\n🛑 Simulation interrupted by user")
        print(f"📊 Final Stats:")
        print(f"   Pieces processed: {stats['pieces_processed']}")
        print(f"   Messages sent: {stats['messages_sent']}")
        runtime = datetime.now() - stats['start_time']
        print(f"   Runtime: {runtime}")
        
        if mqtt_client:
            mqtt_client.disconnect()
        sys.exit(0)
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🏭 Starting Enhanced IoT Industrial Simulator...")
    print(f"⚡ Time multiplier: {TIME_MULTIPLIER}x")
    print(f"📦 Pieces to process: {PIECE_COUNT}")
    print(f"📡 MQTT Broker: {BROKER_ADDRESS}:{BROKER_PORT}")
    print("Press Ctrl+C to stop simulation\n")

    try:
        mqtt_client = MQTTClient(BROKER_ADDRESS, BROKER_PORT)
        machines = {
            name: Machine(name, mtype, mqtt_client, TIME_MULTIPLIER)
            for name, mtype in (
                ("Saw1", "Saw"),
                ("Milling1", "Milling"),
                ("Milling2", "Milling"),
                ("Lathe1", "Lathe"),
            )
        }

        # Enhanced plan with more variety
        plan_templates = [
            ("Milling1", "steel", "Milling", ["TM10", "TM25"]),
            ("Milling2", "aluminum", "Milling", ["TM12", "TM30"]),
            ("Lathe1", "steel", "Lathe", ["TL05"]),
            ("Lathe1", "brass", "Lathe", ["TL08"]),
            ("Milling1", "titanium", "Milling", ["TM15", "TM35"]),
        ]
        
        plan = []
        for idx in range(PIECE_COUNT):
            template = plan_templates[idx % len(plan_templates)]
            machine, mat, tp, tools = template
            plan.append({
                "piece_id": f"PZ{idx+1:03d}", 
                "material": mat, 
                "tools": {tp: tools},
                "route": ["Warehouse", "Saw1", machine, "Warehouse"]
            })

        print(f"📋 Processing {len(plan)} pieces...\n")
        
        for job_idx, job in enumerate(plan, 1):
            try:
                piece = Piece(job["piece_id"], job["route"], job["material"], job["tools"])
                prev = "Warehouse"
                
                print(f"🔄 Processing piece {job_idx}/{len(plan)}: {piece.piece_id} ({job['material']})")

                for station in piece.route[1:-1]:
                    machine = machines[station]
                    
                    # Wait for machine availability
                    wait_count = 0
                    while not machine.is_available():
                        time.sleep(1 / TIME_MULTIPLIER)
                        wait_count += 1
                        if wait_count > 60:  # Safety timeout
                            print(f"⚠️  Timeout waiting for {station}")
                            break

                    if prev != station:
                        # Move piece
                        print(f"  🚛 Moving {piece.piece_id} from {prev} to {station}")
                        publish_tracking_event(mqtt_client, "piece", "move_start",
                            {"piece_id": piece.piece_id, "from": prev, "to": station},
                            simulation_current_time.isoformat())
                        stats['messages_sent'] += 1
                        
                        move_min = get_transport_time(prev, station)
                        simulation_current_time += timedelta(minutes=move_min)
                        time.sleep(move_min * 60 / TIME_MULTIPLIER)
                        
                        publish_tracking_event(mqtt_client, "piece", "move_end",
                            {"piece_id": piece.piece_id, "from": prev, "to": station},
                            simulation_current_time.isoformat())
                        stats['messages_sent'] += 1

                    # Process on machine
                    cycle_min = get_cycle_time_minutes()
                    machine.process(piece.piece_id, cycle_min * 60, simulation_current_time, piece.tools)
                    prev = station
                    simulation_current_time += timedelta(minutes=cycle_min)
                    
                    # Estimate messages sent during processing
                    processing_steps = int(cycle_min * 60 / DATA_SEND_INTERVAL)
                    stats['messages_sent'] += processing_steps + 2  # +2 for start/end events

                # Return to warehouse
                print(f"  🏠 Returning {piece.piece_id} to warehouse")
                publish_tracking_event(mqtt_client, "piece", "move_start",
                    {"piece_id": piece.piece_id, "from": prev, "to": "Warehouse"},
                    simulation_current_time.isoformat())
                
                move_min = get_transport_time(prev, "Warehouse")
                simulation_current_time += timedelta(minutes=move_min)
                time.sleep(move_min * 60 / TIME_MULTIPLIER)
                
                publish_tracking_event(mqtt_client, "piece", "move_end",
                    {"piece_id": piece.piece_id, "from": prev, "to": "Warehouse"},
                    simulation_current_time.isoformat())
                
                publish_tracking_event(mqtt_client, "Warehouse_01", "deposit",
                    {"piece_id": piece.piece_id}, simulation_current_time.isoformat())
                
                stats['messages_sent'] += 3
                stats['pieces_processed'] += 1
                
                print(f"✅ Completed piece {piece.piece_id}\n")

            except Exception as e:
                print(f"❌ Error processing piece {job_idx}: {e}")
                continue

        print(f"🎉 Simulation completed successfully!")
        print(f"📊 Final Statistics:")
        print(f"   Pieces processed: {stats['pieces_processed']}")
        print(f"   Messages sent: {stats['messages_sent']}")
        runtime = datetime.now() - stats['start_time']
        print(f"   Total runtime: {runtime}")
        
        # Keep running for continuous simulation
        print("\n🔄 Starting continuous operation...")
        while True:
            time.sleep(10)
            print(f"📊 {datetime.now().strftime('%H:%M:%S')} - Simulation still running...")
        
    except Exception as e:
        print(f"❌ Simulation error: {e}")
        if mqtt_client:
            mqtt_client.disconnect()
        sys.exit(1)
    finally:
        if mqtt_client:
            mqtt_client.disconnect()