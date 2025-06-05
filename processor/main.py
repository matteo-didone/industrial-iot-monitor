import os
import logging
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv() 

# MQTT Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TIMEOUT = 60
MQTT_TOPIC_DATA = "/plant/data/+"
MQTT_TOPIC_TRACKING = "/plant/tracking/+"

# InfluxDB Configuration
INFLUXDB_URL = f"{os.getenv('INFLUX_ADDRESS', 'http://localhost')}:{int(os.getenv('INFLUX_PORT', '8086'))}"
INFLUXDB_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUX_ORG")
INFLUXDB_BUCKET = os.getenv("INFLUX_BUCKET")

# Global variables
influxdb_client: InfluxDBClient | None = None
influxdb_write = None

def _connection_to_db():
    """Initialize connection to InfluxDB"""
    global influxdb_client, influxdb_write
    
    try:
        logger.info(f"Connecting to InfluxDB at {INFLUXDB_URL}")
        
        influxdb_client = InfluxDBClient(
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG
        )
        
        # Test connection
        influxdb_client.ping()
        logger.info("✅ InfluxDB connection successful")
        
        influxdb_write = influxdb_client.write_api(write_options=SYNCHRONOUS)
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to connect to InfluxDB: {e}")
        return False

def write_sensor_data(entity: str, timestamp: str, data: dict):
    """Write sensor data to InfluxDB"""
    if not influxdb_write:
        logger.warning("InfluxDB writer not available, skipping write")
        return
    
    try:
        # Create point for sensor data
        point = Point("sensor_data") \
            .tag("entity", entity) \
            .tag("machine_type", entity.split("1")[0] if "1" in entity else entity) \
            .time(timestamp)
        
        # Add all numeric fields
        for key, value in data.items():
            if isinstance(value, (int, float)) and value is not None:
                point = point.field(key, float(value))
        
        # Write to InfluxDB
        influxdb_write.write(bucket=INFLUXDB_BUCKET, record=point)
        logger.debug(f"📝 Sensor data written: {entity}")
        
    except Exception as e:
        logger.error(f"❌ Failed to write sensor data: {e}")

def write_tracking_event(entity: str, event: str, timestamp: str, data: dict):
    """Write tracking event to InfluxDB"""
    if not influxdb_write:
        logger.warning("InfluxDB writer not available, skipping write")
        return
    
    try:
        # Create point for tracking events
        point = Point("tracking_events") \
            .tag("entity", entity) \
            .tag("event", event) \
            .time(timestamp)
        
        # Add event-specific data as tags and fields
        for key, value in data.items():
            if isinstance(value, str):
                point = point.tag(key, value)
            elif isinstance(value, (int, float)) and value is not None:
                point = point.field(key, float(value))
        
        # Add event counter for aggregations
        point = point.field("count", 1)
        
        # Write to InfluxDB
        influxdb_write.write(bucket=INFLUXDB_BUCKET, record=point)
        logger.debug(f"📝 Tracking event written: {entity} - {event}")
        
    except Exception as e:
        logger.error(f"❌ Failed to write tracking event: {e}")

def handle_data_message(msg_dict):
    """Handle sensor data messages"""
    entity = msg_dict.get("entity")
    timestamp = msg_dict.get("timestamp")
    data = msg_dict.get("data", {})
    
    # Extract sensor values
    temperature = data.get("temperature")
    power = data.get("power")
    blade_speed = data.get("blade_speed")
    rpm_spindle = data.get("rpm_spindle")
    feed_rate = data.get("feed_rate")
    vibration_level = data.get("vibration_level")
    material_feed = data.get("material_feed")
    cut_depth = data.get("cut_depth")

    # Log sensor data based on machine type
    if entity.startswith("Saw"):
        logger.info(f"[DATA] {entity}: temp={temperature}, power={power}, "
                   f"bladeSpeed={blade_speed}, materialFeed={material_feed}")
    elif entity.startswith("Milling"):
        logger.info(f"[DATA] {entity}: temp={temperature}, power={power}, "
                   f"rpmSpindle={rpm_spindle}, feedRate={feed_rate}, "
                   f"vibrationLevel={vibration_level}")
    elif entity.startswith("Lathe"):
        logger.info(f"[DATA] {entity}: temp={temperature}, power={power}, "
                   f"rpmSpindle={rpm_spindle}, cutDepth={cut_depth}")
    
    # Write to InfluxDB
    write_sensor_data(entity, timestamp, data)

def handle_tracking_message(msg_dict):
    """Handle tracking/event messages"""
    entity = msg_dict.get("entity")
    event = msg_dict.get("event")
    timestamp = msg_dict.get("timestamp")
    data = msg_dict.get("data", {})
    
    piece_id = data.get("piece_id")
    piece_from = data.get("from")
    piece_to = data.get("to")
    tool = data.get("tool")

    logger.info(f"[TRACKING] {entity}: event={event}, pieceId={piece_id}, "
               f"from={piece_from}, to={piece_to}, tool={tool}")
    
    # Write to InfluxDB
    write_tracking_event(entity, event, timestamp, data)

def _mqtt_on_connect(client, userdata, flags, rc, properties=None):
    """Callback for MQTT connection"""
    if rc == 0:
        logger.info("✅ Connected to MQTT broker")
        client.subscribe(MQTT_TOPIC_DATA)
        client.subscribe(MQTT_TOPIC_TRACKING)
        logger.info(f"📡 Subscribed to topics: {MQTT_TOPIC_DATA}, {MQTT_TOPIC_TRACKING}")
    else:
        logger.error(f"❌ Failed to connect to MQTT broker, code: {rc}")

def _mqtt_on_disconnect(client, userdata, rc, properties=None):
    """Callback for MQTT disconnection"""
    if rc != 0:
        logger.warning("⚠️  Unexpected MQTT disconnection")

def _mqtt_on_message(client, userdata, msg):
    """Callback for received MQTT messages"""
    try:
        msg_dict = json.loads(msg.payload.decode())
        topic = msg.topic

        if topic.startswith("/plant/data/"):
            handle_data_message(msg_dict)
        elif topic.startswith("/plant/tracking/"):
            handle_tracking_message(msg_dict)
        else:
            logger.warning(f"⚠️  Unknown topic: {topic}")

    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON decode error: {e}")
    except Exception as e:
        logger.error(f"❌ Error processing message: {e}")

def main():
    """Main function"""
    logger.info("🏭 Starting Industrial IoT Event Processor...")
    logger.info(f"📡 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    logger.info(f"💾 InfluxDB: {INFLUXDB_URL}")
    
    # Initialize MQTT client
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = _mqtt_on_connect
    client.on_disconnect = _mqtt_on_disconnect
    client.on_message = _mqtt_on_message
    
    try:
        # Connect to InfluxDB
        if not _connection_to_db():
            logger.error("❌ Failed to connect to InfluxDB, exiting...")
            return
        
        # Connect to MQTT broker
        logger.info("🔌 Connecting to MQTT broker...")
        client.connect(MQTT_BROKER, MQTT_PORT, MQTT_TIMEOUT)
        
        # Start processing messages
        logger.info("🚀 Event processor is running... Press Ctrl+C to stop")
        client.loop_forever()

    except KeyboardInterrupt:
        logger.info("🛑 Program stopped by user")
    except Exception as exc:
        logger.error(f"❌ Fatal error: {exc}")
    finally:
        # Clean shutdown
        logger.info("🧹 Cleaning up...")
        client.disconnect()
        if influxdb_client:
            influxdb_client.close()
        logger.info("👋 Event processor stopped")

if __name__ == "__main__":
    main()