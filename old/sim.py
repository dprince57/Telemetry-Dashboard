#!/usr/bin/env python3
"""
This runs the main race simulation and communicates with pit wall server.
"""

import time
import os
import TrackHandler as td
import CarHandler as ch
from concurrent.futures import ThreadPoolExecutor, as_completed

Delta_Time = 0.05  # 20Hz


def simulate_car_step(car, dt, track, sim_t, all_cars):
    try:
        lap_event = ch.run_sim(car, dt, track, sim_t, all_cars=all_cars)
        return car.car_id, lap_event, None
    except Exception as e:
        return car.car_id, None, str(e)


def print_race_status(cars, sim_t):
    minutes = int(sim_t // 60)
    seconds = sim_t % 60
    
    print(f"\n{'='*80}")
    print(f"Race Time: {minutes:02d}:{seconds:05.2f}")
    print(f"{'='*80}")
    
    # Sort by position
    cars_sorted = sorted(cars, key=lambda c: (-c.laps, -c.track_position))
    
    print(f"{'Pos':<4} {'Car':<4} {'Laps':<5} {'Fuel':<7} {'Tire%':<7} {'G-Total':<8} {'Pits':<5} {'Status':<15}")
    print("-" * 80)
    
    for i, car in enumerate(cars_sorted, 1):
        avg_tire_wear = (car.tire_FL.wear + car.tire_FR.wear + 
                        car.tire_RL.wear + car.tire_RR.wear) / 4.0
        
        status = ""
        if car.in_pit_lane:
            status = "IN PIT"
        elif car.is_drafting:
            status = f"DRAFT {car.car_ahead_id}"
        elif car.overtake_side != "none":
            status = f"OVERTAKE-{car.overtake_side.upper()}"
        
        print(f"{i:<4} {car.car_id:<4} {car.laps:<5} "
              f"{car.carSpec.fuel_onboard_kg:<7.1f} {avg_tire_wear*100:<6.1f}% "
              f"{car.gforces.total:<8.2f} {car.pit_stops_completed:<5} {status:<15}")


def main():
    print("=" * 80)
    print("RACE SIMULATION - 192.168.0.213")
    print("Connecting to Pit Wall: 192.168.0.212:5000")
    print("=" * 80)
    track = td.load_track("tracks/cota.yaml", "weather/weather.yaml")
    
    num_cars = 10
    cars = []

    # Only these cars are shown on the pit wall dashboard and can receive pit commands
    PLAYER_IDS = {"0", "1"}

    for i in range(num_cars):
        car_id = str(i)
        is_player = car_id in PLAYER_IDS

        car = ch.init_car(
            i,
            "specs/gt3_spec.yaml",
            aggression=0.6 + (i % 3) * 0.1,
            is_player=is_player,
        )
        # Stagger starting positions
        car.track_position = i * 15.0
        cars.append(car)
    
    print(f"Cars on track: {len(cars)}")
    print(f"Track: {getattr(track, 'name', 'Unknown')}")
    print(f"Track length: {track.lap_length_meter:.0f}m")
    print("=" * 80)
    print("NOTE: Telemetry sent to pit wall every 0.5 seconds")
    print("      Pit commands received from pit wall server")
    print("      Access pit wall: http://192.168.0.212:5000")
    print("=" * 80)
    
    # Simulation parameters
    max_laps = 20
    sim_t = 0.0
    
    # Status print interval
    status_print_interval = 10.0
    last_status_print = 0.0
    
    # Threading
    max_workers = min(len(cars), os.cpu_count() or 4)
    
    print(f"Running on {max_workers} threads")
    print("=" * 80)
    
    start_time = time.time()
    
    # Main simulation loop
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while not all(car.laps >= max_laps for car in cars):
            # Submit all car simulations in parallel
            futures = []
            for car in cars:
                future = executor.submit(simulate_car_step, car, Delta_Time, track, sim_t, cars)
                futures.append(future)
            
            # Wait for all cars to complete this timestep
            errors = []
            for future in as_completed(futures):
                car_id, lap_event, error = future.result()
                if error:
                    errors.append(f"Car {car_id}: {error}")
            
            if errors:
                print("Errors during simulation:")
                for err in errors:
                    print(f"  {err}")
            
            sim_t += Delta_Time
            
            if sim_t - last_status_print >= status_print_interval:
                print_race_status(cars, sim_t)
                last_status_print = sim_t
            
            time.sleep(Delta_Time)
    
    # Race complete
    end_time = time.time()
    pro_time = end_time - start_time
    minutesp = pro_time / 60
    secondsp = pro_time % 60
    
    print("\n" + "=" * 80)
    print("RACE COMPLETE!")
    print("=" * 80)
    print(f"Total simulation time: {minutesp:.0f}:{secondsp:.2f}")
    print(f"Speedup: {(sim_t / pro_time):.2f}x realtime")
    print("=" * 80)
    
    # Final results
    print("\nFinal Results:")
    print("-" * 80)
    cars_sorted = sorted(cars, key=lambda c: (-c.laps, -c.track_position))
    
    for position, car in enumerate(cars_sorted, 1):
        avg_tire_wear = (car.tire_FL.wear + car.tire_FR.wear + 
                        car.tire_RL.wear + car.tire_RR.wear) / 4.0
        
        if car.best_lap > 60.0:
            minutes = car.best_lap / 60
            seconds = car.best_lap % 60
            lap_time_str = f"{minutes:.0f}:{seconds:.2f}"
        else:
            lap_time_str = f"{car.best_lap:.2f}s"
        
        print(f"{position:2d}. Car {car.car_id} | "
              f"Laps: {car.laps:2d} | "
              f"Best: {lap_time_str} | "
              f"Pits: {car.pit_stops_completed} ({car.total_pit_time:.1f}s) | "
              f"Fuel: {car.carSpec.fuel_onboard_kg:.1f}kg | "
              f"Tires: {avg_tire_wear*100:.1f}%")
    
    print("\n" + "=" * 80)
    print("G-FORCE STATISTICS")
    print("=" * 80)
    for car in cars[:3]:
        print(f"Car {car.car_id}:")
        print(f"  Current G-Total: {car.gforces.total:.2f}G")
        print(f"  Longitudinal: {car.gforces.longitudinal:+.2f}G")
        print(f"  Lateral: {car.gforces.lateral:.2f}G")
        print(f"  Vertical: {car.gforces.vertical:.2f}G")


if __name__ == "__main__":
    main()

