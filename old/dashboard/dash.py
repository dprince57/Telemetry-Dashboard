#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template
from datetime import datetime
import sys

app = Flask(__name__)

# Show these as the "two drivers" in cards/profile
PLAYER_CAR_IDS = ["0", "1"]

# Track map config (temporary constants until you add /track endpoint)
TRACK_CFG = {
    "name": "cota",
    "lap_length_meter": 5513.0,
    "pit_entry_position": 5400.0,
    "pit_exit_position": 200.0,
}

strategy_mode = "manual"
telemetry_data = {}   # car_id -> dict
pit_commands = {}     # car_id -> dict


@app.route("/")
def index():
    return render_template(
        "index.html",
        mode=strategy_mode,
        player_ids=PLAYER_CAR_IDS,
        track=TRACK_CFG,
    )


@app.route("/telemetry", methods=["POST"])
def receive_telemetry():
    data = request.json or {}
    car_id = str(data.get("car_id", ""))

    if not car_id:
        return jsonify({"status": "error", "error": "missing car_id"}), 400

    data["last_update"] = datetime.now().isoformat()
    telemetry_data[car_id] = data
    return jsonify({"status": "ok"})


@app.route("/telemetry_all", methods=["GET"])
def get_all_telemetry():
    # IMPORTANT: return ALL cars so the map can render everyone
    return jsonify(telemetry_data)


@app.route("/pit_command/<car_id>", methods=["GET"])
def get_pit_command(car_id):
    car_id = str(car_id)
    if car_id in pit_commands:
        cmd = pit_commands[car_id]
        del pit_commands[car_id]
        return jsonify(cmd)
    return jsonify({"should_pit": False})


@app.route("/pit", methods=["POST"])
def send_pit_command():
    data = request.json or {}
    car_id = str(data.get("car_id", ""))

    if not car_id:
        return jsonify({"error": "car_id required"}), 400

    # only allow pit calls for the two player cars
    if car_id not in PLAYER_CAR_IDS:
        return jsonify({"error": "not a player car"}), 403

    pit_commands[car_id] = {
        "should_pit": True,
        "change_tires": bool(data.get("change_tires", True)),
        "refuel_amount_kg": float(data.get("refuel_amount_kg", 0.0)),
    }
    return jsonify({"status": "success", "car_id": car_id})


def run_server(mode="manual"):
    global strategy_mode
    strategy_mode = mode
    print("=" * 60)
    print("PIT WALL SERVER")
    print("=" * 60)
    print(f"Mode: {strategy_mode}")
    print("Listening on: 0.0.0.0:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    mode = "manual"
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    run_server(mode)

