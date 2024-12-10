# ------------ Import Required Libraries ------------

import os
import board
import busio
import threading
import RPi.GPIO as GPIO
from flask import Flask, jsonify
from adafruit_bme280 import basic as adafruit_bme280
from flask_cors import CORS
from datetime import datetime
import atexit
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import time
import pytz
from supabase import create_client
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# ------------ Load Environment Variables ------------

load_dotenv()

# ------------ Flask App Initialization ------------

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Enable CORS for all routes

# ------------ Constants ------------

RAIN_PER_PULSE = 0.061  # Rain measurement per sensor pulse in mm
IR_THRESHOLD = 0.35  # Voltage threshold for detecting rain
MIN_TIP_INTERVAL = 0.05  # Minimum time between rain tip detections in seconds

# ------------ Supabase Client Initialization ------------

key = os.environ.get("SUPABASE_KEY")
url = os.environ.get("SUPABASE_URL")
supabase = create_client(url, key)
print("Supabase client initialized")  # Debug: Check if Supabase is initialized

# ------------ Sensor Manager Class ------------

class SensorManager:
    """
    Handles initialization and data retrieval for sensors, 
    including BME280 and ADS1115 (rain and UV sensors).
    """
    def __init__(self):
        self.i2c = busio.I2C(board.SCL, board.SDA)  # Initialize I2C communication
        self.bme280 = self.initialize_BMEsensor()  # Initialize BME280 sensor
        self.adc = self.initialize_ADC()  # Initialize ADS1115 ADC
        self.rain_count = 0  # Counter for rain tips
        self.state = False  # State of the rain sensor
        self.monitoring = False  # Rain monitoring flag

    def initialize_BMEsensor(self):
        """Initialize BME280 sensor for temperature, humidity, and pressure readings."""
        try:
            bme280 = adafruit_bme280.Adafruit_BME280_I2C(self.i2c, address=0x76)
            bme280.sea_level_pressure = 1013.25  # Set sea level pressure
            print("BME280 sensor initialized")
            return bme280
        except Exception as e:
            print(f"Error initializing BME280 sensor: {str(e)}")
            return None

    def initialize_ADC(self):
        """Initialize ADS1115 ADC for analog sensor readings."""
        try:
            adc = ADS.ADS1115(self.i2c)
            print("ADS1115 ADC initialized")
            return adc
        except Exception as e:
            print(f"Error initializing ADS1115 ADC: {str(e)}")
            return None

    def check_rain_tip(self):
        """
        Check rain sensor voltage to detect rain events.
        Increment rain count if rain is detected.
        """
        try:
            if not self.adc:
                print("ADS1115 not initialized")
                return
            
            channel = AnalogIn(self.adc, ADS.P0)  # Read from rain sensor channel
            voltage = channel.voltage
            # Detect rain based on voltage threshold
            if not self.state and voltage < IR_THRESHOLD:
                self.rain_count += 1
                self.state = True
                print(f"Rain detected! Total rain count: {self.rain_count}")
            elif voltage >= IR_THRESHOLD:
                self.state = False
        except Exception as e:
            print(f"Error in check_rain_tip: {str(e)}")

    def start_rain_monitoring(self):
        """Start a separate thread to monitor rain continuously."""
        self.monitoring = True
        self.rain_thread = threading.Thread(target=self._rain_monitor_loop)
        self.rain_thread.daemon = True
        self.rain_thread.start()
        print("Rain monitoring started")

    def _rain_monitor_loop(self):
        """Thread loop for monitoring rain tips."""
        while self.monitoring:
            self.check_rain_tip()
            time.sleep(MIN_TIP_INTERVAL)

    def get_readings(self):
        """
        Retrieve data from all sensors and return as a dictionary.
        Includes temperature, humidity, pressure, UV index, and precipitation.
        """
        if not self.bme280 or not self.adc:
            print("One or more sensors not initialized")
            return None
            
        try:
            sensor_data = {
                'temperature': round(self.bme280.temperature, 2),
                'humidity': round(self.bme280.relative_humidity, 2),
                'pressure': round(self.bme280.pressure, 2),
                'altitude': round(self.bme280.altitude, 2)
            }
            uv_channel = AnalogIn(self.adc, ADS.P1)  # Read UV sensor channel
            uv_voltage = uv_channel.voltage
            uv_index = max((uv_voltage - 1.0) * 7.5, 0)  # Calculate UV index
            sensor_data['uv_index'] = round(uv_index, 2)
            sensor_data['precipitation'] = round(self.rain_count * RAIN_PER_PULSE, 2)
            sensor_data['time'] = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%Y-%m-%d %H:%M:%S')
            print("Sensor data retrieved:", sensor_data)
            return sensor_data
        except Exception as e:
            print(f"Error reading sensor data: {str(e)}")
            return None

# ------------ Database Manager Class ------------

class DatabaseManager:
    """Handles communication with the database."""
    
    def db_post(self, values):
        """Insert sensor data into the database."""
        try:
            data = supabase.table("hourly_conditions").insert(values).execute()
            print("Data sent to database:", data)
        except Exception as e:
            print(f"Failed to send data to database: {e}")
            
    def db_get(self):
        """Retrieve data from the database."""
        try:
            data = supabase.table("hourly_conditions").select("*").execute()
            print("Data retrieved from database")
            return data
        except Exception as e:
            print(f"Failed to get data from database: {e}")
            return None
    
    def db_realTime(self, values):
        """Insert real-time sensor data into the database."""
        try:
            supabase.table("real_time").insert(values).execute()
            response = supabase.table("real_time").select("*").order('id', desc=False).execute()
        except Exception as e:
            print(f"Failed to insert real-time data: {e}")
            return None

database_manager = DatabaseManager()
sensor_manager = SensorManager()

# ------------ Cleanup Function ------------

def cleanup():
    """Cleanup resources on application exit."""
    try:
        sensor_manager.monitoring = False
        GPIO.cleanup()
    except Exception as e:
        print(f"Cleanup failed: {str(e)}")

# ------------ Scheduler Functions ------------

def fetch_and_store_data():
    """Fetch sensor data and store in database at regular intervals."""
    sensor_data = sensor_manager.get_readings()
    if sensor_data:
        database_manager.db_post(sensor_data)
    else:
        print("No sensor data available to store in the database")

def fetch_and_store_realtime_data():
    """Fetch real-time sensor data and store in database."""
    sensor_data = sensor_manager.get_readings()
    if sensor_data:
        database_manager.db_realTime(sensor_data)
    else:
        print("No real-time sensor data available to store")

def db_scheduler():
    """Start a scheduler for periodic data storage."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_and_store_data, 'interval', minutes=20)
    scheduler.start()
    print("Scheduler started for fetch_and_store_data every 20 minutes")

def real_time_scheduler():
    """Start a scheduler for real-time data storage."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_and_store_realtime_data, 'interval', minutes=2)
    scheduler.start()
    print("Scheduler started for fetch_and_store_realtime_data every 2 minutes")

# ------------ Main Application Entry Point ------------

if __name__ == '__main__':
    atexit.register(cleanup)  # Ensure cleanup on exit

    sensor_manager.start_rain_monitoring()
    db_scheduler()
    real_time_scheduler()
    app.run(host='0.0.0.0', port=5003, debug=False)
