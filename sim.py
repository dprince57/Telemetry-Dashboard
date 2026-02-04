#!/usr/bin/env python3

import time
import math
import TrackHandler as td
import CarHandler as ch

DT = 0.05 #roughly 5Hz


def main():
    track = td.load_track("tracks/cota.yaml", "weather/weather.yaml")
    car = ch.init_car("81", "specs/spec.yaml")
    print(f"{track.name}\n{car.car_id}")
    
main()
