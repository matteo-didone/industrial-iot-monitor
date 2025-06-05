import time
import random
import threading
import os
from datetime import datetime, timedelta
import numpy as np
import paho.mqtt.client as mqtt
import json
from concurrent.futures import ThreadPoolExecutor

# Simulation parameters from environment
DATA_SEND_INTERVAL = 3  # seconds between payloads (simulated)
NOMINAL_CYCLE_MIN = 6   # average processing time (minutes) - faster for demo
SIGMA_CYCLE_MIN = 1.0   # standard deviation (minutes)

# Transfer times between stations (minutes) - faster for demo
DIST_MIN = {
    ("Saw1", "Milling1"): 0.5,
    ("Saw1", "Lathe1"): 0.5,
    ("Saw1", "Milling2"): 0.5,
    ("Milling1", "Lathe1"): 0.3,
    ("Milling2", "Lathe1"): 0.3,
}
DEFAULT_MOVE_MIN = 0.5

# Factory clock
simulation_current_time = datetime.now()
time_lock = threading.Lock()

def get_transport_time(from_station: str, to_station: str) -> float:
    """Returns transport time (minutes) with ±20% jitter."""
    base = DIST_MIN.get(
        (from_station, to_station),
        DIST_MIN.get((to_station, from_station), DEFAULT_MOVE_MIN)
    )
    jitter = random.uniform(-0.1, 0.1) * base
    return max(0.2, base + jitter)

def get_cycle_time_minutes() -> float:
    """Returns a normally distributed cycle time (min), truncated at ≥1 min."""
    return max(2.0, np.random.normal(NOMINAL_CYCLE_MIN, SIGMA_CYCLE_MIN))

class MQTTClient:
    """Thread-safe MQTT client"""
    def __init__(self, broker_address, broker_port):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.broker_address = broker_address
        self.broker_port = broker_port
        self.connected = False
        self.publish_lock = threading.Lock()
        
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
            while not self.connected and retry_count < 15:
                time.sleep(1)
                retry_count += 1
            
            if self.connected:
                print(f"✅ Connected to MQTT broker")
            else:
                raise ConnectionError("Failed to connect after 15 retries")
                
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
        with self.publish_lock:
            if self.connected:
                try:
                    result = self.client.publish(topic, json.dumps(payload))
                    if result.rc != mqtt.MQTT_ERR_SUCCESS:
                        print(f"⚠️  Failed to publish to {topic}")
                    else:
                        print(f"📤 [{payload.get('entity', 'unknown')}] Published to {topic}")
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
    """Thread-safe machine simulation."""
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
        """Simulates realistic sensor data."""
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

        # Enhanced thermal model for more realistic temperatures
        heat_input = power * self.heat_coeff
        if self.busy:
            heat_input *= 2.0  # More heat when processing
        
        dT = (heat_input - (self.current_temp - self.ambient_temp) / self.thermal_time_const) * dt
        self.current_temp += dT + random.uniform(-0.3, 0.3)
        
        # Keep temperature in realistic range
        self.current_temp = max(18.0, min(85.0, self.current_temp))

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
        """Thread-safe availability check."""
        with self.lock:
            return not self.busy

    def set_busy(self, busy: bool):
        """Thread-safe busy state setter."""
        with self.lock:
            self.busy = busy

    def _publish_event(self, topic: str, payload: dict) -> None:
        """Helper to publish MQTT messages."""
        self.mqtt.publish(topic, payload)

    def _run_simulation(self, duration_s: float, piece_id: str) -> None:
        """Runs sensor data simulation over the specified duration."""
        steps = int(duration_s / DATA_SEND_INTERVAL)
        print(f"  📊 [{self.name}] Running {steps} sensor readings for piece {piece_id}...")
        
        for step in range(steps):
            try:
                data = self.simulate_variable_data(DATA_SEND_INTERVAL)
                with time_lock:
                    current_time = datetime.now()
                
                payload = {"entity": self.name, "data": data, "timestamp": current_time.isoformat()}
                self._publish_event(f"/plant/data/{self.name}", payload)

                time.sleep(DATA_SEND_INTERVAL / self.time_multiplier)
            except Exception as e:
                print(f"❌ [{self.name}] Error in simulation step: {e}")
                break

    def setup_tool(self, tool: str) -> None:
        """Performs tool setup, including wear incrementation."""
        setup_min = random.uniform(1, 2)  # Faster setup for demo
        duration_s = setup_min * 60

        self.state = "setup"
        print(f"  🔧 [{self.name}] Setting up tool {tool}...")
        
        with time_lock:
            current_time = datetime.now()
        
        self._publish_event(f"/plant/tracking/{self.name}", {
            "entity": self.name,
            "event": "setup_start",
            "data": {"tool": tool},
            "timestamp": current_time.isoformat(),
        })

        time.sleep(duration_s / self.time_multiplier)

        # Update tool and wear
        self.current_tool = tool
        self.tool_wear[tool] = min(1.0, self.tool_wear.get(tool, 0.0) + 0.03)

        with time_lock:
            current_time = datetime.now()

        self._publish_event(f"/plant/tracking/{self.name}", {
            "entity": self.name,
            "event": "setup_end",
            "data": {"tool": tool},
            "timestamp": current_time.isoformat(),
        })
        self.state = "idle"

    def process(self, piece_id: str, duration_s: float, tools_map: dict) -> None:
        """Processes a piece in time slices per required tools."""
        tool_list = tools_map.get(self.type, [None])
        adjusted = duration_s * random.uniform(0.7, 1.3)  # More variation
        slice_s = adjusted / len(tool_list)

        print(f"  ⚙️ [{self.name}] Processing {piece_id} with tools {tool_list}")

        for tool in tool_list:
            if self.type in ("Milling", "Lathe") and tool != self.current_tool:
                self.setup_tool(tool)

            self.state = "processing"
            self.set_busy(True)
            
            with time_lock:
                current_time = datetime.now()
            
            self._publish_event(f"/plant/tracking/{self.name}", {
                "entity": self.name,
                "event": "processing_start",
                "data": {"piece_id": piece_id, "tool": tool},
                "timestamp": current_time.isoformat(),
            })

            self._run_simulation(slice_s, piece_id)

            with time_lock:
                current_time = datetime.now()
            
            self._publish_event(f"/plant/tracking/{self.name}", {
                "entity": self.name,
                "event": "processing_end",
                "data": {"piece_id": piece_id, "tool": tool},
                "timestamp": current_time.isoformat(),
            })

            self.state = "idle"
            self.set_busy(False)

def publish_tracking_event(mqtt_client: MQTTClient, entity: str, event: str, data: dict) -> None:
    """Publishes a generic tracking event."""
    with time_lock:
        current_time = datetime.now()
    
    mqtt_client.publish(f"/plant/tracking/{entity}", {
        "entity": entity, 
        "event": event, 
        "data": data, 
        "timestamp": current_time.isoformat()
    })

def process_piece_thread(piece, machines, mqtt_client, stats):
    """Process a single piece in its own thread."""
    try:
        piece_obj = Piece(piece["piece_id"], piece["route"], piece["material"], piece["tools"])
        prev = "Warehouse"
        
        print(f"\n🔄 [Thread-{piece['piece_id']}] Processing {piece_obj.piece_id} ({piece['material']})")

        for station in piece_obj.route[1:-1]:
            machine = machines[station]
            
            # Wait for machine availability with timeout
            wait_count = 0
            max_wait = 30  # Reduced timeout for faster demo
            while not machine.is_available() and wait_count < max_wait:
                time.sleep(0.5)
                wait_count += 1
            
            if wait_count >= max_wait:
                print(f"⚠️ [{piece_obj.piece_id}] Timeout waiting for {station}, skipping...")
                continue

            if prev != station:
                # Move piece
                print(f"  🚛 [{piece_obj.piece_id}] Moving from {prev} to {station}")
                publish_tracking_event(mqtt_client, "piece", "move_start",
                    {"piece_id": piece_obj.piece_id, "from": prev, "to": station})
                
                move_min = get_transport_time(prev, station)
                time.sleep(move_min * 60 / 8.0)  # Fast movement for demo
                
                publish_tracking_event(mqtt_client, "piece", "move_end",
                    {"piece_id": piece_obj.piece_id, "from": prev, "to": station})

            # Process on machine
            cycle_min = get_cycle_time_minutes()
            machine.process(piece_obj.piece_id, cycle_min * 60, piece_obj.tools)
            prev = station

        # Return to warehouse
        print(f"  🏠 [{piece_obj.piece_id}] Returning to warehouse")
        publish_tracking_event(mqtt_client, "piece", "move_start",
            {"piece_id": piece_obj.piece_id, "from": prev, "to": "Warehouse"})
        
        move_min = get_transport_time(prev, "Warehouse")
        time.sleep(move_min * 60 / 8.0)
        
        publish_tracking_event(mqtt_client, "piece", "move_end",
            {"piece_id": piece_obj.piece_id, "from": prev, "to": "Warehouse"})
        
        publish_tracking_event(mqtt_client, "Warehouse_01", "deposit",
            {"piece_id": piece_obj.piece_id})
        
        with threading.Lock():
            stats['pieces_processed'] += 1
        
        print(f"✅ [{piece_obj.piece_id}] Completed processing")

    except Exception as e:
        print(f"❌ [Thread-{piece['piece_id']}] Error: {e}")

if __name__ == "__main__":
    import signal
    import sys
    
    # Configuration from environment variables
    BROKER_ADDRESS = os.getenv('MQTT_BROKER', 'localhost')
    BROKER_PORT = int(os.getenv('MQTT_PORT', '1883'))
    TIME_MULTIPLIER = float(os.getenv('TIME_MULTIPLIER', '8.0'))
    PIECE_COUNT = int(os.getenv('PIECE_COUNT', '20'))  # More pieces for demo

    # Statistics
    stats = {'pieces_processed': 0, 'messages_sent': 0, 'start_time': datetime.now()}
    mqtt_client = None
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully"""
        print(f"\n🛑 Simulation interrupted by user")
        print(f"📊 Final Stats:")
        print(f"   Pieces processed: {stats['pieces_processed']}")
        runtime = datetime.now() - stats['start_time']
        print(f"   Total runtime: {runtime}")
        
        if mqtt_client:
            mqtt_client.disconnect()
        sys.exit(0)
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🏭 Starting PARALLEL IoT Industrial Simulator for DEMO...")
    print(f"⚡ Time multiplier: {TIME_MULTIPLIER}x")
    print(f"📦 Pieces to process: {PIECE_COUNT}")
    print(f"📡 MQTT Broker: {BROKER_ADDRESS}:{BROKER_PORT}")
    print(f"🔀 PARALLEL PROCESSING: Multiple machines will be active simultaneously!")
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

        # Enhanced plan with guaranteed parallel processing
        plan_templates = [
            ("Milling1", "steel", "Milling", ["TM10", "TM25"]),
            ("Milling2", "aluminum", "Milling", ["TM12", "TM30"]),
            ("Lathe1", "steel", "Lathe", ["TL05"]),
            ("Lathe1", "brass", "Lathe", ["TL08"]),
            ("Milling1", "titanium", "Milling", ["TM15", "TM35"]),
            ("Milling2", "copper", "Milling", ["TM20", "TM40"]),
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

        print(f"📋 Processing {len(plan)} pieces in PARALLEL...\n")
        
        # Process pieces in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as executor:  # Allow up to 6 concurrent pieces
            futures = []
            
            for i, piece in enumerate(plan):
                # Stagger the start times to create overlap
                if i > 0:
                    time.sleep(3)  # 3 second stagger between piece starts
                
                future = executor.submit(process_piece_thread, piece, machines, mqtt_client, stats)
                futures.append(future)
                print(f"🚀 Started processing thread for {piece['piece_id']}")
            
            print(f"\n🔀 All {len(plan)} pieces started in parallel!")
            print("🎯 Dashboard should now show multiple active machines!")
            
            # Wait for all pieces to complete
            for future in futures:
                try:
                    future.result(timeout=300)  # 5 minute timeout per piece
                except Exception as e:
                    print(f"❌ Piece processing error: {e}")

        print(f"\n🎉 Parallel simulation completed!")
        print(f"📊 Final Statistics:")
        print(f"   Pieces processed: {stats['pieces_processed']}")
        runtime = datetime.now() - stats['start_time']
        print(f"   Total runtime: {runtime}")
        
        # Continue with continuous operation
        print("\n🔄 Starting continuous parallel operation for demo...")
        continuous_count = 0
        while True:
            continuous_count += 1
            print(f"\n🔄 Continuous cycle {continuous_count} - Starting 4 pieces simultaneously...")
            
            # Start 4 pieces simultaneously (one for each machine type)
            simultaneous_pieces = [
                {"piece_id": f"DEMO{continuous_count:02d}-A", "material": "steel", "tools": {"Milling": ["TM10"]}, "route": ["Warehouse", "Saw1", "Milling1", "Warehouse"]},
                {"piece_id": f"DEMO{continuous_count:02d}-B", "material": "aluminum", "tools": {"Milling": ["TM12"]}, "route": ["Warehouse", "Saw1", "Milling2", "Warehouse"]},
                {"piece_id": f"DEMO{continuous_count:02d}-C", "material": "brass", "tools": {"Lathe": ["TL05"]}, "route": ["Warehouse", "Saw1", "Lathe1", "Warehouse"]},
                {"piece_id": f"DEMO{continuous_count:02d}-D", "material": "titanium", "tools": {"Milling": ["TM15"]}, "route": ["Warehouse", "Saw1", "Milling1", "Warehouse"]},
            ]
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(process_piece_thread, piece, machines, mqtt_client, stats) 
                        for piece in simultaneous_pieces]
                
                # Wait for this batch to complete
                for future in futures:
                    try:
                        future.result(timeout=180)
                    except Exception as e:
                        print(f"❌ Continuous cycle error: {e}")
            
            print(f"✅ Continuous cycle {continuous_count} completed")
            time.sleep(5)  # Brief pause between cycles
        
    except Exception as e:
        print(f"❌ Simulation error: {e}")
        if mqtt_client:
            mqtt_client.disconnect()
        sys.exit(1)
    finally:
        if mqtt_client:
            mqtt_client.disconnect()