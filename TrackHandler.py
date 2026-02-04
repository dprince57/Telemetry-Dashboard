from dataclasses import dataclass
import math
import yaml
from pathlib import Path

@dataclass
class Weather:
    temp: float

@dataclass
class Segment:
    type: str
    s_meter: float
    e_meter: float
    speed_limit_mps: float | None = None
    target_speed_mps: float | None = None
    label: str | None = None
    radius_meter: float | None = None
    direction: str | None = None

@dataclass
class Track:
    name: str
    lap_length_meter: float
    segments: list[Segment]
    weather: Weather

def load_track(path: str, weather: str) -> Track:
    with open(path ,"r") as f:
        raw_track = yaml.safe_load(f)
    segs = []
    for item in raw_track["segments"]:
        segs.append(Segment(**item))

    with open(weather, "r") as w:
        raw_weather = yaml.safe_load(w)

    return Track(name=raw_track["name"], lap_length_meter=float(raw_track["lap_length_meter"]), segments=segs, weather=raw_weather)
