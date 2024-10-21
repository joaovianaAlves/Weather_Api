import board
import logging
from flask import Flask, jsonify, make_response, request
from adafruit_bme280 import basic as adafruit_bme280
from datetime import datetime

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

try:
    i2c = board.I2C()
    bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
    bme280.sea_level_pressure = 1013.25
except Exception as e:
    logging.error(f"Error initializing BME280 sensor: {str(e)}")
    bme280 = None

@app.route('/', methods=["GET", "OPTIONS"])
def get_sensor_data():
    if request.method == "OPTIONS":
        return _build_cors_preflight_response()
    elif request.method == "GET":
        if bme280 is None:
            logging.error("BME280 sensor not initialized")
            return jsonify({'error': 'Sensor not initialized'}), 500

        try:
            temperature = round(bme280.temperature, 2)
            humidity = round(bme280.relative_humidity, 2)
            pressure = round(bme280.pressure, 2)
            altitude = round(bme280.altitude, 2)
            time = datetime.now()

            data = {
                'temperature': temperature,
                'humidity': humidity,
                'pressure': pressure,
                'altitude': altitude,
                'time': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            response = jsonify(data)
            return _corsify_actual_response(response)
        except Exception as e:
            logging.error(f"Error reading sensor data: {str(e)}")
            return jsonify({'error': 'Error reading sensor data'}), 500
    else:
        raise RuntimeError("Weird - don't know how to handle method {}".format(request.method))

def _build_cors_preflight_response():
    response = make_response()
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add('Access-Control-Allow-Headers', "*")
    response.headers.add('Access-Control-Allow-Methods', "*")
    return response

def _corsify_actual_response(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response

if __name__ == '__main__':
    print("Weather Station is running. Access it at http://[RaspberryPi_IP]:5002")
    print("Press CTRL+C to quit")

    app.run(host='0.0.0.0', port=5002, debug=False)