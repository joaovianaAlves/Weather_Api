
import os
import board
import logging
import atexit
from flask import Flask, render_template, jsonify
from adafruit_bme280 import basic as adafruit_bme280
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from collections import defaultdict

logging.basicConfig(level=logging.INFO)

data = []
app = Flask(__name__)
CORS(app)

try:
    i2c = board.I2C()
    bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
    bme280.sea_level_pressure = 1013.25
except Exception as e:
    logging.error(f"Error initializing BME280 sensor: {str(e)}")
    bme280 = None

def get_sensor_data():
    if bme280 is None:
        logging.error("BME280 sensor not initialized")
        return {'error': 'Sensor not initialized'}

    try:
        temperature = round(bme280.temperature, 2)
        humidity = round(bme280.relative_humidity, 2)
        pressure = round(bme280.pressure, 2)
        altitude = round(bme280.altitude, 2)
        time = datetime.now()

        return {
            'temperature': temperature,
            'humidity': humidity,
            'pressure': pressure,
            'altitude': altitude,
            'time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        logging.error(f"Error reading sensor data: {str(e)}")
        return {'error': 'Error reading sensor data'}

def store_sensor_data():
    sensor_data = get_sensor_data()
    if 'error' not in sensor_data:
        data.append(sensor_data)
        logging.info(f"Stored sensor data: {data}")
        if(len(data) >= 12):
            data.pop(0)

@app.route('/', methods=["GET"])
def get_latest_data():
    if not data:
        return jsonify({'error': 'No data available'}), 404
    return jsonify(data[-1])

@app.route('/history', methods=["GET"])
def get_history():
    return jsonify(data)

if __name__ == '__main__':
    print("Weather Station is running. Access it at http://[RaspberryPi_IP]:5002")
    print("Press CTRL+C to quit")

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=store_sensor_data, trigger="interval", seconds=1)
    scheduler.start()

    atexit.register(lambda: scheduler.shutdown())

    app.run(host='0.0.0.0', port=5002, debug=False)