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
    best_lap: float = 0.0

def init_car(car_id: int, spec_path: str) -> CarState:
    with open(spec_path,"r") as f:
        raw_spec = yaml.safe_load(f)
    return CarState(car_id = car_id, carSpec = raw_spec)

def run_sim(car: CarState, dt: float, track: TrackHandler.Track, sim_t: float) -> dict | None:

    #Sections will be commented out for easier manipulation of data and code

    #----------Variables I think I need-----------

    old_pos = car.track_position

    #----------Velocity and distance--------------
    
    if car.velocity_mps < 75.0:
        old_speed = car.velocity_mps
        car.velocity_mps += car.acceleration_mps * dt
        car.track_position += ((car.velocity_mps+old_speed)/2) * dt
    else:
        car.track_position += car.velocity_mps * dt

    #----------Lapping logic----------------------

    if car.track_position >= track.lap_length_meter:
 
        minutes = sim_t/60
        seconds = sim_t%60
        print(f"Current Time:{minutes:.0f}:{seconds:.2f}")
        

        distance_from_start = track.lap_length_meter - car.track_position
        distance_traveled = car.track_position - old_pos
        time_frac = distance_from_start / distance_traveled if distance_traveled > 0 else 0.0
        crossing_time = (sim_t - dt) + time_frac * dt
        car.laps += 1
        car.best_lap = crossing_time
        car.track_position -= track.lap_length_meter


#    print(f"Speed: {car.velocity_mps}, Track_position: {car.track_position}")
    return{"t": sim_t, "car_id":car.car_id, "v_mps":car.velocity_mps, "x_m":car.track_position,
            "laps":car.laps,}

