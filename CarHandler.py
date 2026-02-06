import yaml
from dataclasses import dataclass
from pathlib import Path
import TrackHandler
import math
import time

G = 9.81

#hard coded physics for now.
#a_brake = 10
buffer_m = 5
rho_default  = 1.225


@dataclass
class TireState:
    temp_C: float = 70.0
    wear: float = 0.0

@dataclass
class CarSpec:
    fuel_onboard_kg: float
    car_weight_kg: float
    tire_file: str
    aero_file: str
    engine_file: str
    brake_file: str
    
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
    braking_zone: float = -1.0
    braking_meter: float = 0.0
    velo_target: float = 0.0
    tire_FL: TireState = field(default_factory=TireState)
    tire_FR: TireState = field(default_factory=TireState)
    tire_RL: TireState = field(default_factory=TireState)
    tire_RR: TireState = field(default_factory=TireState)
    brake_FL_C: float = 200.0
    brake_FR_C: float = 200.0
    brake_RL_C: float = 200.0
    brake_RR_C: float = 200.0
    tire_params: dict | None = None
    aero_params: dict | None = None
    engine_params: dict | None = None
    brake_params: dict | None = None
    mu_effective: float = 1.3
    throttle: float = 0.0
    brake: float = 0.0
    rpm: float = 1200.0
    gear: int = 1
    shift_timer: float = 0.0
    active_corner_start: float = -2.0
    active_corner_apex: float = -2.0
    active_corner_exit: float = -2.0

def init_car(car_id: int, spec_path: str) -> CarState:
    with open(spec_path,"r") as f:
        raw_spec = yaml.safe_load(f)
    spec = CarSpec(**raw_spec)

    car = CarState(car_id=str(car_id), carSpec=spec)
    with open(spec.tire_file, "r") as tf:
        car.tire_params = yaml.safe_load(tf)
    with open(spec.aero_file, "r") as af:
        car.aero_params = yaml.safe_load(af)
    with open(spec.engine_file, "r") as ef:
        car.engine_params = yaml.safe_load(ef)
    with open(spec.brake_file, "r") as bf:
        car.brake_params = yaml.safe_load(bf)

    return car

def run_sim(car: CarState, dt: float, track: TrackHandler.Track, sim_t: float) -> dict | None:

    #Sections will be commented out for easier manipulation of data and code
    mass = car.carSpec.car_weight_kg+car.carSpec.fuel_onboard_kg
    
    start_time = time.time()
    #----------Determine future events now!-------
    if car.track_position >= car.braking_zone:
        found = False
        for seg in track.segments:
            if seg.type == "corner" and seg.s_meter > car.track_position:
                car.braking_zone = seg.s_meter
                car.velo_target = math.sqrt(car.mu_effective * G * seg.radius_meter)
                #print(car.braking_zone)
                found = True
                break
        if not found:
            for seg in track.segments:
                if seg.type == "corner":
                    car.braking_zone = seg.s_meter
                    car.velo_target = math.sqrt(car.mu_effective * G * seg.radius_meter)
                    break
    if car.velocity_mps > car.velo_target:
        car.braking_meter = (car.velocity_mps**2 - car.velo_target**2) / (2 * a_brake)
    else:
        car.braking_meter = 0.0

    #----------Variables I think I need-----------

    old_pos = car.track_position
    old_speed = car.velocity_mps
    
    #-----------Aero modeling----------------------------------
    rho = rho_default
    ClA = 0.0
    CdA = 0.0
    if car.aero_params is not None:
        rho = float(car.aero_params.get("rho", rho))
        ClA = float(car.aero_params.get("ClA", 0.0))
        CdA = float(car.aero_params.get("CdA", 0.0))

    v = car.velocity_mps
    F_down = 0.5 * rho * ClA * v * v
    F_drag = 0.5 * rho * CdA * v * v

    #----------Tire Modeling and grip?-------------------------
    tp = car.tire_params
    if tp is not None:
        mu_peak_ref = float(tp["mu_peak_ref"])
        Fz_ref_N = float(tp["Fz_ref_N"])
        k_mu = float(tp["load_sensitivity"]["k_mu"])

        optC = float(tp["temperature"]["optimal_C"])
        coldC = float(tp["temperature"]["cold_C"])
        hotC = float(tp["temperature"]["hot_C"])
        drop_cold = float(tp["temperature"]["grip_drop_cold"])
        drop_hot = float(tp["temperature"]["grip_drop_hot"])

        mu_drop_wear = float(tp["wear"]["mu_drop_at_full_wear"])
        Fz_total = mass * G + F_down
        Fz_tire = Fz_total / 4.0

        load_ratio = max(0.1, Fz_tire / max(1e-6, Fz_ref_N))
        mu_load = mu_peak_ref * (1.0 - k_mu * math.log(load_ratio))

        mu_list = []
        for tire in [car.tire_FL, car.tire_FR, car.tire_RL, car.tire_RR]:
            T = tire.temp_C
            if T <= coldC:
                f_temp = 1.0 - drop_cold
            elif T >= hotC:
                f_temp = 1.0 - drop_hot
            else:
                if T <= optC:
                    f_temp = (1.0 - drop_cold) + (T - coldC) * (drop_cold / max(1e-6, (optC - coldC)))
                else:
                    f_temp = (1.0 - drop_hot) + (hotC - T) * (drop_hot / max(1e-6, (hotC - optC)))
                f_temp = max(0.2, min(1.0, f_temp))

            w = max(0.0, min(1.0, tire.wear))
            f_wear = 1.0 - (mu_drop_wear * w)

            mu_list.append(max(0.2, mu_load * f_temp * f_wear))

        car.mu_effective = sum(mu_list) / len(mu_list)
    else:
        car.mu_effective = 1.30


    #----------Velocity and distance and braking?--------------
    
    distance_to_zone = car.braking_zone - car.track_position
    if distance_to_zone < 0:
        distance_to_zone += track.lap_length_meter
    if distance_to_zone <= car.braking_meter + buffer_m:
        car.velocity_mps = max(car.velo_target, car.velocity_mps - a_brake * dt)
        car.track_position += ((car.velocity_mps+old_speed)/2) * dt
    elif car.velocity_mps < 75.0:
        car.velocity_mps += car.acceleration_mps * dt
        car.track_position += ((car.velocity_mps+old_speed)/2) * dt
    else:
        car.track_position += car.velocity_mps * dt

    #----------Lapping logic----------------------

    if car.track_position >= track.lap_length_meter:
 
        minutes = sim_t / 60
        seconds = sim_t % 60
        print(f"Current Time:{minutes:.0f}:{seconds:.2f}")
        
        #------------calculate actual lap time based on distance past the line----------------i
        distance_from_start = track.lap_length_meter - old_pos
        distance_traveled = car.track_position - old_pos
        time_frac = distance_from_start / distance_traveled if distance_traveled > 0 else 0.0
        crossing_time = (sim_t - dt) + time_frac * dt
        car.laps += 1
        car.best_lap = crossing_time
        car.track_position -= track.lap_length_meter

    #'''
    print(f"Speed: {car.velocity_mps:.1f}, Track_position: {car.track_position:.1f}\nBraking meters and zone: {car.braking_meter:.1f} {car.braking_zone}\nVelo_target: {car.velo_target:.1f}")
    
    end_time = time.time()
    process_time = end_time - start_time
    print(f"process time: {process_time:.4f}")

    #'''
    return{"t": sim_t, "car_id":car.car_id, "v_mps":car.velocity_mps, "x_m":car.track_position,
            "laps":car.laps,}

    
