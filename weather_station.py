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
load_dotenv()

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

RAIN_PER_PULSE = 0.061
IR_THRESHOLD = 0.35
MIN_TIP_INTERVAL = 0.05
key = os.environ.get("SUPABASE_KEY")
url = os.environ.get("SUPABASE_URL")
supabase = create_client(url, key)
print("Supabase client initialized")  # Debug statement

class SensorManager:
    def __init__(self):
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.bme280 = self.initialize_BMEsensor()
        self.adc = self.initialize_ADC()
        self.rain_count = 0
        self.state = False
        self.monitoring = False

    def initialize_BMEsensor(self):
        try:
            bme280 = adafruit_bme280.Adafruit_BME280_I2C(self.i2c, address=0x76)
            bme280.sea_level_pressure = 1013.25
            print("BME280 sensor initialized")
            return bme280
        except Exception as e:
            print(f"Error initializing BME280 sensor: {str(e)}")
            return None

    def initialize_ADC(self):
        try:
            adc = ADS.ADS1115(self.i2c)
            print("ADS1115 ADC initialized")
            return adc
        except Exception as e:
            print(f"Error initializing ADS1115 ADC: {str(e)}")
            return None

    def check_rain_tip(self):
        try:
            if not self.adc:
                print("ADS1115 not initialized")
                return
            
            channel = AnalogIn(self.adc, ADS.P0) 
            voltage = channel.voltage
            # print(f"Rain sensor voltage: {voltage}, {self.state}")
            
            if not self.state and voltage < IR_THRESHOLD:
                self.rain_count += 1
                self.state = True
                print(f"Rain detected! Total rain count: {self.rain_count}")
            
            elif voltage >= IR_THRESHOLD:
                self.state = False
                
        except Exception as e:
            print(f"Error in check_rain_tip: {str(e)}")
    
    def start_rain_monitoring(self):
        self.monitoring = True
        self.rain_thread = threading.Thread(target=self._rain_monitor_loop)
        self.rain_thread.daemon = True
        self.rain_thread.start()
        print("Rain monitoring started")
        print(self.monitoring)

    def _rain_monitor_loop(self):
        while self.monitoring:
            self.check_rain_tip()
            time.sleep(MIN_TIP_INTERVAL)
    
    def get_readings(self):
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
            uv_channel = AnalogIn(self.adc, ADS.P1)
            uv_voltage = uv_channel.voltage
            uv_index = max((uv_voltage - 1.0) * 7.5, 0)
            sensor_data['uv_index'] = round(uv_index, 2)
            sensor_data['precipitation'] = round(self.rain_count * RAIN_PER_PULSE, 2)
            sensor_data['time'] = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%Y-%m-%d %H:%M:%S')
            print("Sensor data retrieved:", sensor_data)
            return sensor_data
        
        except Exception as e:
            print(f"Error reading sensor data: {str(e)}")
            return None

class DatabaseManager:
    def db_post(self, values):
        try:
            data = supabase.table("hourly_conditions").insert(values).execute()
            print("Data sent to database:", data)
        except Exception as e:
            print(f"Failed to send data to database: {e}")
            
    def db_get(self):
        try:
            data = supabase.table("hourly_conditions").select("*").execute()
            print("Data retrieved from database")
            return data
        except Exception as e:
            print(f"Failed to get data from database: {e}")
            return None
        
    def db_realTime(self, values):
        try:
            supabase.table("real_time").insert(values).execute()
            response = supabase.table("real_time").select("*").order('id', desc=False).execute()
            data = response.data
            if len(data) > 1:
                ids_to_delete = [record['id'] for record in data[:-1]]
                print(f"Deleting records with IDs: {ids_to_delete}")

                supabase.table("real_time").delete().in_('id', ids_to_delete).execute()
        except Exception as e:
            print(f"Failed to get data from database: {e}")
            return None
    
database_manager = DatabaseManager()
sensor_manager = SensorManager()

def cleanup():
    try:
        sensor_manager.monitoring = False
        GPIO.cleanup()
    except Exception as e:
        print(f"Cleanup failed: {str(e)}")

def fetch_and_store_data():
    sensor_data = sensor_manager.get_readings()
    if sensor_data:
        database_manager.db_post(sensor_data)
    else:
        print("No sensor data available to store in the database")

def fetch_and_store_realtime_data():
    sensor_data = sensor_manager.get_readings()
    if sensor_data:
        database_manager.db_realTime(sensor_data)
    else:
        print("No sensor data available to store in the database")
        
def db_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_and_store_data, 'interval', minutes=20)
    scheduler.start()
    print("Scheduler started for fetch_and_store_data every 20 minutes")
    
def real_time_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_and_store_realtime_data, 'interval', minutes=2)
    scheduler.start()
    print("Scheduler started for fetch_and_store_data every 2 minutes")

if __name__ == '__main__':
    atexit.register(cleanup)

    sensor_manager.start_rain_monitoring()
    db_scheduler()
    real_time_scheduler()
    app.run(host='0.0.0.0', port=5003, debug=False)
