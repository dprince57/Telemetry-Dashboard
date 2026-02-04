#!/usr/bin/env python3

import time
import math
import TrackHandler as td

DT = 0.05 #roughly 5Hz


def main():
    track = td.load_track("tracks/cota.yaml", "weather/weather.yaml")
    print(track)
    
main()
