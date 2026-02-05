import yaml
from dataclasses import dataclass
from pathlib import Path
import TrackHandler
import math

G = 9.81

#hard coded physics for now.
mu = 1.3
a_brake = 10
buffer_m = 5


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
    lap_start_time: float = 0.0
    best_lap: float = 0.0
    braking_zone: float = 0.0
    braking_meter: float = 0.0
    velo_target: float = 0.0

def init_car(car_id: int, spec_path: str) -> CarState:
    with open(spec_path,"r") as f:
        raw_spec = yaml.safe_load(f)
    return CarState(car_id = car_id, carSpec = raw_spec)

def run_sim(car: CarState, dt: float, track: TrackHandler.Track, sim_t: float) -> dict | None:

    #Sections will be commented out for easier manipulation of data and code

    #----------Determine future events now!-------
    if car.track_position > car.braking_zone:
        for seg in track.segments:
            if seg.type == "corner" and seg.s_meter > car.track_position:
                car.braking_zone = seg.s_meter
                car.velo_target = math.sqrt(mu * G * seg.radius_meter)
                print(car.braking_zone)
                break
    car.braking_meter = (car.velocity_mps - car.velo_target) / 2 * a_brake

    #----------Variables I think I need-----------

    old_pos = car.track_position

    #----------Velocity and distance and braking?--------------
    if car.braking_zone - car.braking_meter < car.track_position:
        car.velocity_mps = max(car.velo_target, car.velocity_mps - a_brake * dt)
    elif car.velocity_mps < 75.0:
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
        
        #------------calculate actual lap time based on distance past the line----------------i
        distance_from_start = car.track_position - track.lap_length_meter
        distance_traveled = car.track_position - old_pos
        time_frac = distance_from_start / distance_traveled if distance_traveled > 0 else 0.0
        crossing_time = (sim_t - dt) + time_frac * dt
        car.laps += 1
        car.best_lap = crossing_time
        car.track_position -= track.lap_length_meter


    print(f"Speed: {car.velocity_mps}, Track_position: {car.track_position}")
    return{"t": sim_t, "car_id":car.car_id, "v_mps":car.velocity_mps, "x_m":car.track_position,
            "laps":car.laps,}

