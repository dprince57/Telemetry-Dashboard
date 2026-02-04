#!/usr/bin/env python3

import time
import math
import TrackHandler as td
import CarHandler as ch

Delta_Time = 0.05 #roughly 5Hz

def main():
    track = td.load_track("tracks/cota.yaml", "weather/weather.yaml")
    car = ch.init_car("81", "specs/spec.yaml")
    print(f"{track.name}\n{car.car_id}")

    max_laps = 5
    sim_t = 0.0

    while True:
        lap_event = ch.run_sim(car, Delta_Time, track, sim_t)

        time.sleep(Delta_Time)


main()
