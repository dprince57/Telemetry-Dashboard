import yaml
from dataclasses import dataclass, field
from pathlib import Path
import TrackHandler
import math
import time

G = 9.81

# Physics constants
buffer_m = 5
rho_default = 1.225


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
    throttle: float = 0.0  # Now analog: 0.0-1.0
    brake: float = 0.0     # Now analog: 0.0-1.0
    rpm: float = 1200.0
    gear: int = 1
    shift_timer: float = 0.0
    active_corner_start: float = -2.0
    active_corner_apex: float = -2.0
    active_corner_exit: float = -2.0
    past_apex: bool = False  # Track if we've passed apex

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


# ============= Helper Functions for run_sim =============

def _find_next_corner(car: CarState, track: TrackHandler.Track) -> bool:
    """Find next corner and update braking zone and target velocity."""
    
    for seg in track.segments:
        if seg.type == "corner" and seg.s_meter > car.track_position:
            car.braking_zone = seg.s_meter
            car.velo_target = math.sqrt(max(0.0, car.mu_effective * G * seg.radius_meter))
            return True
    
    # Wrap around to first corner
    for seg in track.segments:
        if seg.type == "corner":
            car.braking_zone = seg.s_meter
            car.velo_target = math.sqrt(max(0.0, car.mu_effective * G * seg.radius_meter))
            return True
    
    return False


def _get_corner_boundaries(seg: TrackHandler.Segment, default_corner_length: float = 60.0) -> tuple:
    """Extract corner start, apex, and end positions."""
    
    start_s = seg.s_meter
    seg_len = getattr(seg, "length_meter", None)
    end_s = getattr(seg, "end_s_meter", None)
    apex_s = getattr(seg, "apex_s_meter", None)

    if end_s is None:
        end_s = start_s + (float(seg_len) if seg_len is not None else default_corner_length)

    if apex_s is None:
        apex_s = start_s + 0.5 * (end_s - start_s)

    return start_s, apex_s, end_s


def _update_active_corner(car: CarState, track: TrackHandler.Track) -> bool:
    """Update active corner if we've passed the exit."""
    
    need_new_corner = (car.active_corner_exit < 0) or (car.track_position >= car.active_corner_exit)
    
    if not need_new_corner:
        return False

    for seg in track.segments:
        if seg.type == "corner" and seg.s_meter > car.track_position:
            start_s, apex_s, end_s = _get_corner_boundaries(seg)
            car.active_corner_start = start_s
            car.active_corner_apex = apex_s
            car.active_corner_exit = end_s
            car.past_apex = False
            car.velo_target = math.sqrt(max(0.0, car.mu_effective * G * seg.radius_meter))
            return True

    for seg in track.segments:
        if seg.type == "corner":
            start_s, apex_s, end_s = _get_corner_boundaries(seg)
            car.active_corner_start = start_s
            car.active_corner_apex = apex_s
            car.active_corner_exit = end_s
            car.past_apex = False
            car.velo_target = math.sqrt(max(0.0, car.mu_effective * G * seg.radius_meter))
            return True

    return False


def _calculate_aero_forces(car: CarState) -> tuple:
    """Calculate downforce and drag."""
    
    rho = rho_default
    ClA = 0.0
    CdA = 0.0
    
    if car.aero_params is not None:
        rho = float(car.aero_params.get("rho", rho_default))
        ClA = float(car.aero_params.get("ClA", 0.0))
        CdA = float(car.aero_params.get("CdA", 0.0))

    v = car.velocity_mps
    F_down = 0.5 * rho * ClA * v * v
    F_drag = 0.5 * rho * CdA * v * v
    
    return F_down, F_drag


def _calculate_tire_friction(car: CarState, mass: float, F_down: float) -> None:
    """Calculate effective friction coefficient from tire parameters."""
    
    tp = car.tire_params
    
    if tp is None:
        car.mu_effective = 1.30
        return

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


def _calculate_brake_fade(car: CarState) -> tuple:
    """Calculate brake fade and effective braking acceleration.
    Returns (brake_fade, a_brake_eff, brake_temp_avg)"""
    
    a_brake_base = 10.0
    fade_start = 650.0
    fade_end = 950.0
    fade_min = 0.70
    
    if car.brake_params is not None:
        a_brake_base = float(car.brake_params.get("a_brake_base", a_brake_base))
        fade_start = float(car.brake_params.get("fade_start_C", fade_start))
        fade_end = float(car.brake_params.get("fade_end_C", fade_end))
        fade_min = float(car.brake_params.get("fade_min", fade_min))

    brake_temp_avg = (car.brake_FL_C + car.brake_FR_C + car.brake_RL_C + car.brake_RR_C) / 4.0
    
    if brake_temp_avg <= fade_start:
        brake_fade = 1.0
    elif brake_temp_avg >= fade_end:
        brake_fade = fade_min
    else:
        brake_fade = 1.0 - (brake_temp_avg - fade_start) * ((1.0 - fade_min) / max(1e-6, (fade_end - fade_start)))

    mu_ref = 1.30
    grip_scale = max(0.50, min(1.50, car.mu_effective / max(1e-6, mu_ref)))
    a_brake_eff = max(0.5, a_brake_base * grip_scale * brake_fade)

    return brake_fade, a_brake_eff, brake_temp_avg


def _get_distance_to_corner_points(car: CarState, track: TrackHandler.Track) -> tuple:
    """Calculate distances to active corner apex and exit.
    Returns (dist_to_apex, dist_to_exit)"""
    
    dist_to_apex = car.active_corner_apex - car.track_position
    if dist_to_apex < 0:
        dist_to_apex += track.lap_length_meter

    dist_to_exit = car.active_corner_exit - car.track_position
    if dist_to_exit < 0:
        dist_to_exit += track.lap_length_meter

    return dist_to_apex, dist_to_exit


def _calculate_brake_demand(car: CarState, dist_to_apex: float, a_brake_eff: float) -> float:
    """Calculate required braking force as analog value (0.0-1.0).
    
    Implements trail braking: graduated brake release as apex approaches.
    Returns brake demand (0.0-1.0)
    """
    
    # Calculate distance needed to reach target speed
    if car.velocity_mps > car.velo_target and car.velo_target > 0:
        braking_meter = (car.velocity_mps**2 - car.velo_target**2) / (2.0 * max(1e-6, a_brake_eff))
    else:
        braking_meter = 0.0

    car.braking_meter = braking_meter

    # Full brake zone: from braking_meter distance before apex
    full_brake_dist = braking_meter + buffer_m
    
    # Trail braking zone: 0.5m before apex (allows mid-corner adjustments)
    trail_braking_dist = 0.5
    
    if car.velocity_mps <= car.velo_target:
        # Already at target speed
        return 0.0
    
    if not car.past_apex and dist_to_apex <= full_brake_dist:
        # In braking zone before apex
        if dist_to_apex <= trail_braking_dist:
            # Trail braking zone: graduate brake release from 1.0 to 0.0 over final 0.5m
            brake_demand = max(0.0, dist_to_apex / trail_braking_dist)
        else:
            # Full braking zone
            brake_demand = 1.0
        
        return brake_demand
    
    return 0.0


def _calculate_throttle_demand(car: CarState, dist_to_apex: float, a_brake_eff: float) -> float:
    """Calculate required throttle as analog value (0.0-1.0).
    
    - 0.0 before apex in braking zone
    - Ramp up after apex based on corner exit proximity
    - 1.0 on straights
    
    Returns throttle demand (0.0-1.0)
    """
    
    # Recalculate braking distance
    if car.velocity_mps > car.velo_target and car.velo_target > 0:
        braking_meter = (car.velocity_mps**2 - car.velo_target**2) / (2.0 * max(1e-6, a_brake_eff))
    else:
        braking_meter = 0.0

    full_brake_dist = braking_meter + buffer_m
    exit_ramp_dist = 5.0  # Distance to ramp from 0 to full throttle after apex
    
    if car.past_apex:
        # After apex: ramp up throttle over exit_ramp_dist
        # This creates smooth acceleration out of corner
        throttle = min(1.0, 1.0 - (dist_to_apex / exit_ramp_dist))
        return max(0.0, throttle)
    else:
        # Before apex: no throttle if in braking zone
        if dist_to_apex <= full_brake_dist:
            return 0.0
        else:
            # On straight before corner: full throttle
            return 1.0


def _update_throttle_and_brake(car: CarState, dist_to_apex: float, a_brake_eff: float) -> None:
    """Update throttle and brake as analog values (0.0-1.0) with trail braking.
    
    Uses conditional logic: brake OR throttle, never both simultaneously.
    """
    
    if dist_to_apex <= 1.0:
        car.past_apex = True

    brake_demand = _calculate_brake_demand(car, dist_to_apex, a_brake_eff)
    throttle_demand = _calculate_throttle_demand(car, dist_to_apex, a_brake_eff)
    
    # Mutually exclusive: if braking, don't throttle. If throttle, minimal brake.
    if brake_demand > 0.05:
        # In braking zone: prioritize brake
        car.brake = brake_demand
        car.throttle = 0.0
    elif throttle_demand > 0.05:
        # In throttle zone: apply throttle, zero brake
        car.throttle = throttle_demand
        car.brake = 0.0
    else:
        # Coasting zone: both zero
        car.brake = 0.0
        car.throttle = 0.0


def _get_engine_parameters(ep: dict) -> dict:
    """Extract engine parameters with defaults."""
    
    return {
        "idle_rpm": float(ep.get("idle_rpm", 1200.0)),
        "redline_rpm": float(ep.get("redline_rpm", 9000.0)),
        "shift_rpm": float(ep.get("shift_rpm", 8200.0)),
        "downshift_rpm": float(ep.get("downshift_rpm", 2500.0)),
        "gear_ratios": ep.get("gear_ratios", [3.20, 2.30, 1.80, 1.45, 1.20, 1.00]),
        "final_drive": float(ep.get("final_drive", 3.70)),
        "wheel_radius_m": float(ep.get("wheel_radius_m", 0.33)),
        "driveline_eff": float(ep.get("drivetrain_eff", 0.92)),
        "top_speed_cap": float(ep.get("top_speed_cap_mps", 1e9)),
        "shift_time_s": float(ep.get("shift_time_s", 0.18)),
        "torque_curve": ep.get("torque_curve", [[1000, 250], [3000, 380], [6000, 420], [8000, 390], [9000, 320]]),
    }


def _update_gear_and_rpm(car: CarState, engine_params: dict, dt: float) -> None:
    """Update gear and RPM with improved shift logic.
    
    - Natural upshifts at high RPM (not just on throttle)
    - Natural downshifts at low RPM (not just on brake)
    - Blip throttle logic for downshifts
    """
    
    idle_rpm = engine_params["idle_rpm"]
    redline_rpm = engine_params["redline_rpm"]
    shift_rpm = engine_params["shift_rpm"]
    downshift_rpm = engine_params["downshift_rpm"]
    gear_ratios = engine_params["gear_ratios"]
    final_drive = engine_params["final_drive"]
    wheel_radius_m = engine_params["wheel_radius_m"]
    shift_time = engine_params["shift_time_s"]

    max_gear = max(1, len(gear_ratios))
    car.gear = max(1, min(max_gear, car.gear))

    # Update shift timer
    if car.shift_timer > 0.0:
        car.shift_timer = max(0.0, car.shift_timer - dt)

    # Calculate RPM from speed
    wheel_omega = car.velocity_mps / max(1e-6, wheel_radius_m)
    gear_ratio = float(gear_ratios[car.gear - 1])
    rpm_from_speed = wheel_omega * gear_ratio * final_drive * (60.0 / (2.0 * math.pi))
    car.rpm = max(idle_rpm, rpm_from_speed)

    # Handle gear shifts (only if not already shifting)
    if car.shift_timer <= 0.0:
        # UPSHIFT: High RPM + throttle or natural high RPM
        if car.rpm >= shift_rpm and car.gear < max_gear and (car.throttle > 0.3 or car.rpm >= shift_rpm + 200):
            car.gear += 1
            car.shift_timer = shift_time
        
        # DOWNSHIFT: Low RPM + braking (or throttle drops suddenly)
        elif car.rpm <= downshift_rpm and car.gear > 1 and (car.brake > 0.2 or car.throttle < 0.1):
            car.gear -= 1
            car.shift_timer = shift_time

    # Recalculate RPM with new gear
    gear_ratio = float(gear_ratios[car.gear - 1])
    rpm_from_speed = wheel_omega * gear_ratio * final_drive * (60.0 / (2.0 * math.pi))
    car.rpm = max(idle_rpm, min(redline_rpm, rpm_from_speed))


def _calculate_torque(car: CarState, engine_params: dict) -> float:
    """Calculate engine torque based on RPM and throttle input."""
    
    torque_curve = engine_params["torque_curve"]
    rpm_now = car.rpm

    # Find torque at current RPM via linear interpolation
    torque_Nm = float(torque_curve[0][1])
    if rpm_now <= float(torque_curve[0][0]):
        torque_Nm = float(torque_curve[0][1])
    elif rpm_now >= float(torque_curve[-1][0]):
        torque_Nm = float(torque_curve[-1][1])
    else:
        for i in range(len(torque_curve) - 1):
            r0 = float(torque_curve[i][0])
            t0 = float(torque_curve[i][1])
            r1 = float(torque_curve[i + 1][0])
            t1 = float(torque_curve[i + 1][1])
            if r0 <= rpm_now <= r1:
                alpha = (rpm_now - r0) / max(1e-6, (r1 - r0))
                torque_Nm = t0 + alpha * (t1 - t0)
                break

    # Apply throttle scaling (analog)
    torque_Nm *= max(0.0, min(1.0, car.throttle))

    # Zero torque during gear shift
    if car.shift_timer > 0.0:
        torque_Nm = 0.0

    return torque_Nm


def _calculate_driving_force(car: CarState, mass: float, F_down: float, engine_params: dict) -> tuple:
    """Calculate net driving force and components.
    Returns (F_drive, F_brake, F_rr, F_drag, F_net, a)"""
    
    torque_Nm = _calculate_torque(car, engine_params)

    gear_ratios = engine_params["gear_ratios"]
    final_drive = engine_params["final_drive"]
    wheel_radius_m = engine_params["wheel_radius_m"]
    driveline_eff = engine_params["driveline_eff"]

    # Calculate wheel force from engine
    gear_ratio = float(gear_ratios[car.gear - 1])
    wheel_torque = torque_Nm * gear_ratio * final_drive * driveline_eff
    F_drive = wheel_torque / max(1e-6, wheel_radius_m)

    # Limit by traction
    Fz_total = mass * G + F_down
    F_trac_max = car.mu_effective * Fz_total
    F_drive = max(-F_trac_max, min(F_trac_max, F_drive))

    # Braking force (analog)
    _, a_brake_eff, _ = _calculate_brake_fade(car)
    F_brake = car.brake * a_brake_eff * mass

    # Rolling resistance
    Crr = 0.015
    tp = car.tire_params
    if tp is not None and "rr" in tp and "Crr" in tp["rr"]:
        Crr = float(tp["rr"]["Crr"])
    F_rr = Crr * Fz_total

    # Drag
    _, F_drag = _calculate_aero_forces(car)

    F_net = F_drive - F_drag - F_rr - F_brake
    a = F_net / max(1e-6, mass)

    return F_drive, F_brake, F_rr, F_drag, F_net, a


def _apply_tire_heating_and_wear(car: CarState, dt: float, ep: dict) -> None:
    """Update tire temperature and wear."""
    
    cool_rate = float(ep.get("tire_cool_rate", 0.08))
    heat_brake = float(ep.get("tire_heat_brake", 18.0))
    heat_accel = float(ep.get("tire_heat_accel", 8.0))
    wear_brake = float(ep.get("tire_wear_brake", 0.0005))
    wear_accel = float(ep.get("tire_wear_accel", 0.0002))

    ambient = 25.0

    # Cool all tires
    for tire in [car.tire_FL, car.tire_FR, car.tire_RL, car.tire_RR]:
        tire.temp_C -= cool_rate * (tire.temp_C - ambient) * dt
        tire.temp_C = max(0.0, tire.temp_C)

    # Apply heating and wear based on brake/throttle (analog)
    if car.brake > 0.1:
        brake_factor = car.brake  # 0.0-1.0
        car.tire_FL.temp_C += heat_brake * brake_factor * dt
        car.tire_FR.temp_C += heat_brake * brake_factor * dt
        car.tire_RL.temp_C += 0.6 * heat_brake * brake_factor * dt
        car.tire_RR.temp_C += 0.6 * heat_brake * brake_factor * dt

        car.tire_FL.wear += wear_brake * brake_factor * dt
        car.tire_FR.wear += wear_brake * brake_factor * dt
        car.tire_RL.wear += 0.6 * wear_brake * brake_factor * dt
        car.tire_RR.wear += 0.6 * wear_brake * brake_factor * dt
    
    if car.throttle > 0.1:
        throttle_factor = car.throttle  # 0.0-1.0
        car.tire_RL.temp_C += heat_accel * throttle_factor * dt
        car.tire_RR.temp_C += heat_accel * throttle_factor * dt
        car.tire_FL.temp_C += 0.4 * heat_accel * throttle_factor * dt
        car.tire_FR.temp_C += 0.4 * heat_accel * throttle_factor * dt

        car.tire_RL.wear += wear_accel * throttle_factor * dt
        car.tire_RR.wear += wear_accel * throttle_factor * dt
        car.tire_FL.wear += 0.4 * wear_accel * throttle_factor * dt
        car.tire_FR.wear += 0.4 * wear_accel * throttle_factor * dt

    # Clamp wear values
    for tire in [car.tire_FL, car.tire_FR, car.tire_RL, car.tire_RR]:
        tire.wear = max(0.0, min(1.0, tire.wear))


def _apply_brake_heating_and_cooling(car: CarState, dt: float, ep: dict) -> None:
    """Update brake temperatures."""
    
    ambient = 25.0
    brake_cool = float(ep.get("brake_cool_rate", 0.10))
    brake_heat_per_brake = float(ep.get("brake_heat_gain", 120.0))

    # Cool all brakes
    for attr in ["brake_FL_C", "brake_FR_C", "brake_RL_C", "brake_RR_C"]:
        cur = getattr(car, attr)
        cur -= brake_cool * (cur - ambient) * dt
        setattr(car, attr, max(ambient, cur))

    # Apply heating based on brake input (analog)
    if car.brake > 0.0:
        heat = brake_heat_per_brake * car.brake * dt
        car.brake_FL_C += heat
        car.brake_FR_C += heat
        car.brake_RL_C += 0.6 * heat
        car.brake_RR_C += 0.6 * heat


def _handle_lap_completion(car: CarState, track: TrackHandler.Track, dt: float, sim_t: float, old_pos: float) -> None:
    """Handle lap completion logic."""
    
    if car.track_position >= track.lap_length_meter:
        minutes = sim_t / 60
        seconds = sim_t % 60
        print(f"Current Time:{minutes:.0f}:{seconds:.2f}")
        
        # Calculate actual lap time based on crossing position
        distance_from_start = track.lap_length_meter - old_pos
        distance_traveled = car.track_position - old_pos
        time_frac = distance_from_start / distance_traveled if distance_traveled > 0 else 0.0
        crossing_time = (sim_t - dt) + time_frac * dt
        
        car.laps += 1
        car.best_lap = crossing_time
        car.track_position -= track.lap_length_meter


def run_sim(car: CarState, dt: float, track: TrackHandler.Track, sim_t: float) -> dict | None:
    """Main simulation loop for car physics and control."""

    start_time = time.time()
    mass = car.carSpec.car_weight_kg + car.carSpec.fuel_onboard_kg

    # ========== Find initial braking zone if needed ==========
    if car.track_position >= car.braking_zone:
        _find_next_corner(car, track)

    # ========== Store previous state ==========
    old_pos = car.track_position
    old_v = car.velocity_mps

    # ========== Calculate aerodynamic forces ==========
    F_down, F_drag = _calculate_aero_forces(car)

    # ========== Calculate tire friction ==========
    _calculate_tire_friction(car, mass, F_down)

    # ========== Calculate brake fade and effective braking ==========
    brake_fade, a_brake_eff, brake_temp_avg = _calculate_brake_fade(car)

    # ========== Update active corner tracking ==========
    _update_active_corner(car, track)

    # ========== Calculate distances to corner points ==========
    dist_to_apex, dist_to_exit = _get_distance_to_corner_points(car, track)

    # ========== Update throttle and brake with trail braking ==========
    _update_throttle_and_brake(car, dist_to_apex, a_brake_eff)

    # ========== Engine and transmission ==========
    engine_params = _get_engine_parameters(car.engine_params or {})
    _update_gear_and_rpm(car, engine_params, dt)

    # ========== Calculate forces and acceleration ==========
    F_drive, F_brake, F_rr, F_drag_unused, F_net, a = _calculate_driving_force(car, mass, F_down, engine_params)

    # ========== Update velocity and position ==========
    top_speed_cap = engine_params["top_speed_cap"]
    car.velocity_mps = max(0.0, min(top_speed_cap, car.velocity_mps + a * dt))
    car.track_position += ((old_v + car.velocity_mps) / 2.0) * dt

    # ========== Update brake and tire thermal states ==========
    _apply_brake_heating_and_cooling(car, dt, car.engine_params or {})
    _apply_tire_heating_and_wear(car, dt, car.engine_params or {})

    # ========== Handle lap completion ==========
    _handle_lap_completion(car, track, dt, sim_t, old_pos)

    # ========== Debug output ==========
    '''print(
        f"Speed: {car.velocity_mps:.1f} m/s, Pos: {car.track_position:.1f} m | "
        f"mu_eff: {car.mu_effective:.2f} | "
        f"tgt(apex): {car.velo_target:.1f} | "
        f"d_to_apex: {dist_to_apex:.1f} d_need: {car.braking_meter:.1f} | "
        f"throttle: {car.throttle:.2f} brake: {car.brake:.2f} | "
        f"gear: {car.gear} rpm: {car.rpm:.0f} shiftT: {car.shift_timer:.2f} | "
        f"brkTavg: {brake_temp_avg:.0f}C fade:{brake_fade:.2f}"
    )'''

    end_time = time.time()
    process_time = end_time - start_time

    # ========== Return telemetry data ==========
    return {
        "t": sim_t,
        "car_id": car.car_id,
        "v_mps": car.velocity_mps,
        "x_m": car.track_position,
        "laps": car.laps,
        "mu_eff": car.mu_effective,
        "throttle": car.throttle,
        "brake": car.brake,
        "gear": car.gear,
        "rpm": car.rpm,
        "brake_temp_avg_C": brake_temp_avg,
        "downforce_N": F_down,
        "drag_N": F_drag,
    }
