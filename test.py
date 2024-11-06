import board
import time
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

rain_threshold = 3.0
rain_count = 0
state = 0

def check_rain_tip():
    global rain_count, state
    
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    channel = AnalogIn(ads, ADS.P0)
    
    voltage = channel.voltage

    if state == 0 and voltage >= rain_threshold:
        rain_count += 1
        state = 1
        print(f"Rain detected! Total rain count: {rain_count}")
    
    if voltage < rain_threshold:
        state = 0
    
while True:
    check_rain_tip()
    time.sleep(0.05)