import os
import board
import logging
from flask import Flask, jsonify
from adafruit_bme280 import basic as adafruit_bme280
from flask_cors import CORS
from datetime import datetime
from pyngrok import ngrok
import atexit

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

CORS(app, resources={r"/*": { 
    "origins": [
        "https://helpful-smart-chimp.ngrok-free.app",
        "http://helpful-smart-chimp.ngrok-free.app",
        "*"  # Keep this if you need other origins too
    ],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "ngrok-skip-browser-warning", "Authorization", "X-Requested-With"],
}})

bme280 = None

def initialize_sensor():
    global bme280
    try:
        i2c = board.I2C()
        bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
        bme280.sea_level_pressure = 1013.25
        logging.info("BME280 sensor initialized")
    except Exception as e:
        logging.error(f"Error initializing BME280 sensor: {str(e)}")
        bme280 = None

def initialize_ngrok():
    try:
        tunnels = ngrok.connect(
            addr="5002",
            hostname="helpful-smart-chimp.ngrok-free.app",
            proto="http"
        )
        logging.info(f"Ngrok tunnel established at: {tunnels}")
        return "https://helpful-smart-chimp.ngrok-free.app"
    except Exception as e:
        logging.error(f"Error initializing ngrok: {str(e)}")
        return None

def cleanup():
    """Cleanup function to disconnect ngrok tunnel"""
    try:
        ngrok.disconnect()
        ngrok.kill()
        logging.info("Ngrok tunnel closed")
    except:
        pass

initialize_sensor()

def get_sensor_readings():
    global bme280
    if bme280 is None:
        initialize_sensor()
    
    if bme280 is None:
        return None

    try:
        return {
            'temperature': round(bme280.temperature, 2),
            'humidity': round(bme280.relative_humidity, 2),
            'pressure': round(bme280.pressure, 2),
            'altitude': round(bme280.altitude, 2)
        }
    except Exception as e:
        logging.error(f"Error reading sensor data: {str(e)}")
        return None

@app.route('/', methods=["GET"])
def get_sensor_data():
    sensor_data = get_sensor_readings()
    if sensor_data is None:
        logging.error("Failed to read sensor data")
        return jsonify({'error': 'Sensor not initialized or unavailable'}), 500

    sensor_data['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return jsonify(sensor_data)

if __name__ == '__main__':
    atexit.register(cleanup)
    
    public_url = initialize_ngrok()
    
    if public_url:
        print(f"Weather Station is running locally at http://localhost:5002")
        print(f"Public URL: {public_url}")
    else:
        print("Weather Station is running locally at http://localhost:5002")
        print("Warning: Ngrok tunnel could not be established")
    
    print("Press CTRL+C to quit")
    
    app.run(host='0.0.0.0', port=5002, debug=False)