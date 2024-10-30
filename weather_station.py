import os
import board
import busio
import logging
from flask import Flask, jsonify
from adafruit_bme280 import basic as adafruit_bme280
from flask_cors import CORS
from datetime import datetime
from pyngrok import ngrok
import atexit
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

CORS(app, resources={r"/*": { 
    "origins": [
        "https://helpful-smart-chimp.ngrok-free.app",
        "http://helpful-smart-chimp.ngrok-free.app",
        "*"
    ],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "ngrok-skip-browser-warning", "Authorization", "X-Requested-With"],
}})

bme280 = None
adc = None
GAIN = 1

def initialize_BMEsensor():
    global bme280
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
        bme280.sea_level_pressure = 1013.25
        logging.info("BME280 sensor initialized")
    except Exception as e:
        logging.error(f"Error initializing BME280 sensor: {str(e)}")
        bme280 = None
        
def initialize_UVsensor():
    global adc
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        adc = ADS.ADS1115(i2c)
        logging.info("UV sensor initialized")
    except Exception as e:
        logging.error(f"Error initializing UV sensor: {str(e)}")
        adc = None

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

# Initialize sensors
initialize_BMEsensor()
initialize_UVsensor()

def get_sensor_readings():
    global bme280, adc
    # Re-initialize sensors if needed
    if bme280 is None:
        initialize_BMEsensor()
    if adc is None:
        initialize_UVsensor()

    if bme280 is None or adc is None:
        return None

    try:
        # Read BME280 data
        sensor_data = {
            'temperature': round(bme280.temperature, 2),
            'humidity': round(bme280.relative_humidity, 2),
            'pressure': round(bme280.pressure, 2),
            'altitude': round(bme280.altitude, 2)
        }

        # Read UV sensor data
        channel = AnalogIn(adc, ADS.P1)
        uv_voltage = channel.voltage
        logging.info(f"Raw UV sensor voltage: {uv_voltage:.2f} V")

        if uv_voltage < 1.0:
            uv_index = 0
            logging.info("UV voltage is below 1.0V, setting UV index to 0.")
        else:
            uv_index = (uv_voltage - 1.0) * 7.5  # Adjusted scaling factor
            logging.info(f"Calculated UV index: {uv_index:.2f}")

        sensor_data['uv_index'] = round(uv_index, 2), channel.voltage

        return sensor_data
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
