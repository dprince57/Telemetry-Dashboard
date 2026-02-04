import yaml
from dataclasses import dataclass
from pathlib import Path
import TrackHandler

@dataclass
class CarSpec:
    fuel_onboard_kg: float
    car_weight_kg: float

@dataclass
class CarState:
    car_id: str
    carSpec: CarSpec
    velocity_mps: float = 0.0
    track_position: float = 0.0
    acceleration_mps: float = 19.6
    laps: int = 0

def init_car(car_id: int, spec_path: str) -> CarState:
    with open(spec_path,"r") as f:
        raw_spec = yaml.safe_load(f)
    return CarState(car_id = car_id, carSpec = raw_spec)

def run_sim(car: CarState, dt: float, track: TrackHandler.Track, sim_t: float) -> dict | None:
    
    if car.velocity_mps < 75.0:
        car.velocity_mps = car.acceleration_mps * dt



    car.track_position += car.velocity_mps * dt
    
    if car.track_position >= track.lap_length_meter:
        car.laps += 1
        car.track_position -= track.lap_length_meter


    print(f"Speed: {car.velocity_mps}, Track_position: {car.track_position}")
    return{"t": sim_t, "car_id":car.car_id, "v_mps":car.velocity_mps, "x_m":car.track_position,
            "laps":car.laps,}

