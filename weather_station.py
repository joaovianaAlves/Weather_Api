import os
import board
import busio
import logging
import RPi.GPIO as GPIO
from flask import Flask, jsonify
from adafruit_bme280 import basic as adafruit_bme280
from flask_cors import CORS
from datetime import datetime
from pyngrok import ngrok
import atexit
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import time

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://helpful-smart-chimp.ngrok-free.app", "*"], "allow_headers": ["Content-Type"]}})

# Constants
RAIN_PER_PULSE = 0.061  # mm per bucket tip for rain gauge
IR_THRESHOLD = 1.0      # Voltage threshold to detect tipping

class SensorManager:
    def __init__(self):
        self.bme280 = None
        self.adc = None
        self.rain_count = 0
        self.last_ir_value = 4.4  # Expected idle voltage for IR sensor
        
        # Initialize sensors
        self.initialize_sensors()
        
    def initialize_sensors(self):
        self.initialize_BMEsensor()
        self.initialize_IRsensor()

    def initialize_BMEsensor(self):
        """Initialize the BME280 sensor for temperature, humidity, and pressure."""
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
            self.bme280.sea_level_pressure = 1013.25
            logging.info("BME280 sensor initialized")
        except Exception as e:
            logging.error(f"Error initializing BME280 sensor: {str(e)}")
            self.bme280 = None

    def initialize_IRsensor(self):
        """Initialize the ADS1115 sensor for IR detection (rain gauge tipping)."""
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.adc = ADS.ADS1115(i2c)
            logging.info("ADS1115 IR sensor initialized")
        except Exception as e:
            logging.error(f"Error initializing ADS1115 IR sensor: {str(e)}")
            self.adc = None

    def check_rain_tip(self):
        """Checks if rain gauge bucket has tipped based on IR sensor voltage."""
        try:
            if not self.adc:
                logging.error("ADS1115 not initialized")
                return
            
            # Read voltage from the IR sensor on channel P0
            channel = AnalogIn(self.adc, ADS.P0)
            ir_voltage = channel.voltage

            # Detect a tipping event if the voltage drop exceeds the threshold
            if abs(self.last_ir_value - ir_voltage) > IR_THRESHOLD:
                self.rain_count += 1
                logging.info(f"Bucket tipped! Total rain count: {self.rain_count}")
                
                # Debounce delay to prevent multiple triggers
                time.sleep(0.1)  # 100 ms debounce delay

            # Update last IR voltage value
            self.last_ir_value = ir_voltage
        except Exception as e:
            logging.error(f"Error in check_rain_tip: {str(e)}")

    def get_readings(self):
        """Retrieve sensor readings from the BME280 and ADS1115."""
        # Ensure sensors are initialized
        if self.bme280 is None:
            self.initialize_BMEsensor()
        if self.adc is None:
            self.initialize_IRsensor()
        if not self.bme280 or not self.adc:
            logging.error("One or more sensors not initialized")
            return None

        # Perform the rain tipping check
        self.check_rain_tip()
        
        try:
            # Collect BME280 data
            sensor_data = {
                'temperature': round(self.bme280.temperature, 2),
                'humidity': round(self.bme280.relative_humidity, 2),
                'pressure': round(self.bme280.pressure, 2),
                'altitude': round(self.bme280.altitude, 2)
            }
            
            # Collect UV sensor data from ADS1115 on channel P1
            uv_channel = AnalogIn(self.adc, ADS.P1)
            uv_voltage = uv_channel.voltage
            uv_index = (uv_voltage - 1.0) * 7.5 if uv_voltage >= 1.0 else 0
            sensor_data['uv_index'] = round(uv_index, 2)
            
            # Calculate total precipitation
            sensor_data['precipitation'] = round(self.rain_count * RAIN_PER_PULSE, 2)
            
            return sensor_data
        except Exception as e:
            logging.error(f"Error reading sensor data: {str(e)}")
            return None

sensor_manager = SensorManager()

def initialize_ngrok():
    """Initialize Ngrok tunnel for public access."""
    try:
        tunnels = ngrok.connect(addr="5002", hostname="helpful-smart-chimp.ngrok-free.app", proto="http")
        logging.info(f"Ngrok tunnel established at: {tunnels}")
        return "https://helpful-smart-chimp.ngrok-free.app"
    except Exception as e:
        logging.error(f"Error initializing ngrok: {str(e)}")
        return None

def cleanup():
    """Cleanup Ngrok tunnel and GPIO resources on exit."""
    try:
        ngrok.disconnect()
        ngrok.kill()
        GPIO.cleanup()  # Clean up GPIO resources
        logging.info("Ngrok tunnel closed and GPIO cleaned up")
    except Exception as e:
        logging.error(f"Cleanup failed: {str(e)}")

@app.route('/', methods=["GET"])
def get_sensor_data():
    """Endpoint to retrieve current sensor data."""
    sensor_data = sensor_manager.get_readings()
    if sensor_data is None:
        logging.error("Failed to retrieve sensor data")
        return jsonify({'error': 'Sensor not initialized or unavailable'}), 500

    # Add current timestamp
    sensor_data['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return jsonify(sensor_data)

if __name__ == '__main__':
    # Register cleanup on exit
    atexit.register(cleanup)
    
    # Initialize Ngrok and get public URL
    public_url = initialize_ngrok()
    if public_url:
        logging.info(f"Weather Station is running locally at http://localhost:5002")
        logging.info(f"Public URL: {public_url}")
    else:
        logging.warning("Ngrok tunnel could not be established")

    # Start the Flask application
    app.run(host='0.0.0.0', port=5002, debug=False)
