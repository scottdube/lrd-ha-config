#!/usr/bin/env python3
import os
import sys
import csv
from datetime import datetime

LOG_FILE = '/config/pool_temp_log.csv'
HEADERS = ['timestamp', 'water_temp', 'oat', 'heater_state', 'pump_state', 'pump_speed', 'waterfall_state', 'forecast_high', 'swimming_day']

def log_data(water_temp, oat, heater_state, pump_state, pump_speed, waterfall_state, forecast_high, swimming_day):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(HEADERS)
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            water_temp,
            oat,
            heater_state,
            pump_state,
            pump_speed,
            waterfall_state,
            forecast_high,
            swimming_day
        ])

if __name__ == '__main__':
    log_data(
        water_temp=sys.argv[1],
        oat=sys.argv[2],
        heater_state=sys.argv[3],
        pump_state=sys.argv[4],
        pump_speed=sys.argv[5],
        waterfall_state=sys.argv[6],
        forecast_high=sys.argv[7],
        swimming_day=sys.argv[8]
    )
