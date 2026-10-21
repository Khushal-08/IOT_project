"""Single-room IoT dashboard. Run `python app.py` for the local simulator."""
import atexit
import json
import math
import os
import re
import threading
import time
import uuid

from flask import Flask, jsonify, render_template, request
from room_model import RoomModel
from demo_runner import DemoRunner, decisions


class Room(RoomModel):
    def __init__(self, mode="demo", start=True, clock=time.monotonic):
        super().__init__(clock)
        if mode not in {"demo", "mqtt"}:
            raise ValueError("HOME_MODE must be demo or mqtt")
        self.mode = mode
        self.lock = threading.RLock()
        self.command_lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.online = mode == "demo"
        self.last_seen = self.clock() if self.online else 0
        self.last_id = None
        self.last_error = ""
        self.client = None
        self.broker_connected = False
        self.reported_countdown = None
        self.demo_runner = DemoRunner(self)
        self.topic = os.getenv("MQTT_TOPIC", "student/smart-home/room-7e24b1c903-v2").rstrip("/")
        if mode == "mqtt" and start:
            self.start_mqtt()

    def snapshot(self):
        with self.lock:
            online = self.online and (self.mode == "demo" or self.clock() - self.last_seen < 10)
            if self.mode == "demo":
                if online:
                    self.demo_runner.advance()
                self.tick(active=online)
                countdown = max(0, math.ceil(self.empty_until - self.clock())) if self.empty_until is not None else None
            else:
                self.meter(self.clock(), active=online)
                countdown = self.reported_countdown if online else None
            return dict(self.state, online=online, source=self.mode,
                        broker_connected=self.broker_connected,
                        temperature=self.state["temperature"] if online else None,
                        countdown=countdown, events=[dict(event) for event in reversed(self.events)],
                        motion=dict(self.motion), energy=self.energy(),
                        decisions=decisions(self.state, countdown) if online else dict(light="Device unavailable", fan="Device unavailable", alarm="Sensor unavailable"),
                        walkthrough=self.demo_runner.snapshot() if self.mode == "demo" else None,
                        brightness_lux=(650 if self.state["daylight"] else 20) if online else None)

    def automate(self):
        self.policy()

    def start_mqtt(self):
        import paho.mqtt.client as mqtt
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="dashboard-" + uuid.uuid4().hex[:12])
        if os.getenv("MQTT_USERNAME"):
            self.client.username_pw_set(os.getenv("MQTT_USERNAME"), os.getenv("MQTT_PASSWORD"))
        if os.getenv("MQTT_TLS") == "1":
            self.client.tls_set()

        def connected(client, userdata, flags, reason_code, properties):
            self.broker_connected = not reason_code.is_failure
            if self.broker_connected:
                client.subscribe([(self.topic + "/state", 0), (self.topic + "/availability", 0)])

        def disconnected(client, userdata, flags, reason_code, properties):
            with self.condition:
                self.broker_connected = False
                self.online = False
                self.condition.notify_all()

        def message(client, userdata, msg):
            if msg.topic.endswith("/availability"):
                if msg.payload == b"offline":
                    with self.condition:
                        self.online = False
                        self.condition.notify_all()
                return
            # Retained snapshots are historical, not evidence of a live device.
            if msg.retain:
                return
            try:
                data = json.loads(msg.payload)
                temperature = float(data["temperature"])
                if (type(data["temperature"]) not in {int, float} or not math.isfinite(temperature) or not -40 <= temperature <= 80
                        or type(data["light"]) is not bool or type(data["fan"]) is not bool
                        or data["fan_mode"] not in {"manual", "auto"}
                        or data.get("protocol") != 2
                        or type(data.get("people")) is not int or not 0 <= data["people"] <= 8
                        or type(data.get("daylight")) is not bool or type(data.get("smoke")) is not bool
                        or data.get("light_mode") not in {"manual", "auto"}
                        or (data.get("countdown") is not None and (type(data["countdown"]) is not int or not 0 <= data["countdown"] <= 10))):
                    return
                with self.condition:
                    self.meter(self.clock(), active=self.online and self.clock() - self.last_seen < 10)
                    old = dict(self.state)
                    self.state.update({key: data[key] for key in self.state})
                    self.state["temperature"] = temperature
                    self.reported_countdown = data.get("countdown")
                    for key in ("people", "daylight", "smoke", "temperature", "light_mode", "fan_mode", "light", "fan"):
                        if old[key] != self.state[key]:
                            if key in {"light", "fan"}:
                                reason = ("smoke alert" if self.state["smoke"] else "room empty" if self.state["people"] == 0
                                          else "manual override" if self.state[key + "_mode"] == "manual"
                                          else "occupancy + daylight" if key == "light" else "occupancy + temperature")
                                description = f"{key.title()} {'ON' if self.state[key] else 'OFF'} · ESP32 {reason}"
                            else:
                                description = f"ESP32 confirmed · {key.replace('_', ' ')}: {self.state[key]}"
                            self.log(description,
                                     "warning" if key == "smoke" and self.state[key] else "info")
                    if old["people"] != self.state["people"]:
                        self.motion = dict(id=self.motion["id"] + 1,
                                           direction="enter" if self.state["people"] > old["people"] else "exit")
                    self.online = True
                    self.last_seen = self.clock()
                    self.last_id = data.get("id")
                    self.last_error = str(data.get("error", ""))[:200]
                    self.condition.notify_all()
            except (ValueError, KeyError, TypeError):
                pass

        self.client.on_connect = connected
        self.client.on_disconnect = disconnected
        self.client.on_message = message
        self.client.reconnect_delay_set(1, 10)
        self.client.connect_async(os.getenv("MQTT_HOST", "broker.hivemq.com"),
                                  int(os.getenv("MQTT_PORT", "1883")), 15)
        self.client.loop_start()

    def close(self):
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()

    def command(self, device, value):
        self.validate(device, value)
        with self.command_lock:
            with self.condition:
                if not self.snapshot()["online"]:
                    raise ConnectionError("Device unavailable. Reconnect the simulation and try again.")
                if self.mode == "demo":
                    if self.demo_runner.running:
                        self.demo_runner.action("pause")
                    self.apply(device, value)
                    return self.snapshot()
                if self.state["smoke"] and device in {"light", "fan", "light_mode", "fan_mode"}:
                    raise ValueError("Smoke alert is active. Clear smoke first.")
                if device == "entry" and ((value == "exit" and self.state["people"] == 0) or (value == "enter" and self.state["people"] >= 8)):
                    raise ValueError("Room is already empty." if value == "exit" else "Room capacity is 8 people.")
                if device == "temperature":
                    raise ValueError("Change temperature on the DHT22 sensor inside Wokwi.")
                if not self.client or not self.broker_connected:
                    raise ConnectionError("MQTT connection unavailable.")
                command_id = uuid.uuid4().hex
                result = self.client.publish(self.topic + "/command", json.dumps(
                    dict(id=command_id, device=device, value=value)), qos=0, retain=False)
                if result.rc != 0:
                    raise ConnectionError("Could not send command. Please try again.")
                confirmed = self.condition.wait_for(
                    lambda: self.last_id == command_id or not self.online, timeout=5)
                if not confirmed or self.last_id != command_id:
                    raise ConnectionError("Device did not confirm the command. Check its connection.")
                if self.last_error:
                    raise ValueError(self.last_error)
                return self.snapshot()


def parse_command(message):
    text = re.sub(r"[^a-z0-9\s]", " ", message.lower())
    words = text.split()
    tokens = set(words)
    if "smoke" in tokens:
        if tokens & {"clear", "stop", "remove"}:
            return "smoke", False
        if tokens & {"simulate", "trigger", "start"}:
            return "smoke", True
    if tokens & {"enter", "entry"}:
        return "entry", "enter"
    if tokens & {"exit", "leave"}:
        return "entry", "exit"
    if "night" in tokens and "day" not in tokens:
        return "daylight", False
    if "day" in tokens and "night" not in tokens:
        return "daylight", True
    if tokens & {"energy", "usage", "cost"}:
        return "energy", None
    if tokens & {"people", "occupancy"}:
        return "people", None
    if "status" in tokens:
        return "status", None
    if "temperature" in tokens or "temp" in tokens:
        return "temperature", None
    if "mode" in tokens or tokens & {"auto", "automatic", "manual"}:
        device = "light" if tokens & {"light", "lights"} else "fan" if "fan" in tokens else None
        if device:
            if tokens & {"auto", "automatic"} and "manual" not in tokens:
                return device + "_mode", "auto"
            if "manual" in tokens and not tokens & {"auto", "automatic"}:
                return device + "_mode", "manual"
    devices = tokens & {"light", "lights", "fan"}
    if devices and not ({"light", "lights"} & devices and "fan" in devices):
        if ("on" in tokens) != ("off" in tokens):
            return ("fan" if "fan" in devices else "light"), "on" in tokens
    return None, None


def create_app(room=None):
    app = Flask(__name__)
    room = room or Room(os.getenv("HOME_MODE", "demo"))
    app.config["ROOM"] = room
    app.config["MAX_CONTENT_LENGTH"] = 4096
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/state")
    def state():
        response = jsonify(room.snapshot())
        response.headers["Cache-Control"] = "no-store"
        return response

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("Send a JSON object.")
        return data

    @app.post("/api/control")
    def control():
        data = body()
        result = room.command(data.get("device"), data.get("value"))
        return jsonify(state=result, message="Device updated.")

    @app.post("/api/chat")
    def chat():
        message = body().get("message", "")
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 200:
            raise ValueError("Enter a command of 1–200 characters.")
        device, value = parse_command(message)
        if device is None:
            return jsonify(message="Try ‘enter room’, ‘night mode’, ‘fan auto’, ‘simulate smoke’, ‘energy’, or ‘status’.", state=room.snapshot())
        if not room.snapshot()["online"]:
            raise ConnectionError("Device unavailable. Reconnect the simulation and try again.")
        current = room.snapshot() if device in {"status", "temperature", "people", "energy"} else room.command(device, value)
        if device == "temperature":
            reply = f"The room temperature is {current['temperature']:.1f}°C."
        elif device == "status":
            reply = (f"Light: {'on' if current['light'] else 'off'}. "
                     f"Fan: {'on' if current['fan'] else 'off'} ({current['fan_mode']}). "
                     f"Temperature: {current['temperature']:.1f}°C. People: {current['people']}. "
                     f"{'Day' if current['daylight'] else 'Night'}. Smoke: {'ALERT' if current['smoke'] else 'clear'}.")
        elif device in {"fan_mode", "light_mode"}:
            reply = f"{device.split('_')[0].title()} is now in {value} mode."
        elif device == "entry":
            reply = f"Person {'entered' if value == 'enter' else 'left'}. {current['people']} inside."
            if current["countdown"] is not None:
                reply += " Room empty: appliances switch off in 10 seconds."
        elif device == "daylight":
            reply = f"{'Day' if value else 'Night'} selected. Auto lighting follows occupancy and daylight."
        elif device == "smoke":
            reply = "Smoke alert active: visibility light ON, fan OFF. Simulation only." if value else "Smoke cleared. Normal room rules restored."
        elif device == "people":
            reply = f"There are {current['people']} people in the room."
        elif device == "energy":
            e = current["energy"]
            reply = f"Estimated use: {e['total_kwh'] * 1000:.3f} Wh. Estimated cost: ₹{e['cost']:.4f} (9W light, 60W fan, ₹8/kWh)."
        else:
            reply = f"{'Light' if device == 'light' else 'Fan'} turned {'on' if value else 'off'}."
            if device == "fan":
                reply += " Fan is in manual mode."
        return jsonify(message=reply, state=current)

    @app.post("/api/walkthrough")
    def walkthrough():
        if room.mode != "demo":
            return jsonify(message="Automatic walkthrough uses the local simulator."), 403
        with room.lock:
            if not room.online:
                raise ConnectionError("Reconnect the simulator before running the demo.")
            room.demo_runner.action(body().get("action"))
            return jsonify(state=room.snapshot())

    @app.post("/api/demo")
    def demo():
        if room.mode != "demo":
            return jsonify(message="Change sensor readings inside Wokwi in MQTT mode."), 403
        data = body()
        with room.lock:
            if "online" in data and type(data["online"]) is not bool:
                raise ValueError("Connection state must be true or false.")
            if "temperature" in data:
                room.validate("temperature", data["temperature"])
                if not room.online:
                    raise ConnectionError("Reconnect the simulator before changing the temperature.")
                if room.demo_runner.running:
                    room.demo_runner.action("pause")
                room.apply("temperature", float(data["temperature"]))
            if "online" in data:
                room.tick(active=room.online)
                if not data["online"]:
                    room.demo_runner.action("pause")
                room.online = data["online"]
                room.log("Local simulator " + ("reconnected." if room.online else "disconnected."))
            return jsonify(state=room.snapshot())

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(message=str(error)), 400

    @app.errorhandler(ConnectionError)
    def unavailable(error):
        return jsonify(message=str(error), state=room.snapshot()), 503

    return app


if __name__ == "__main__":
    app = create_app()
    atexit.register(app.config["ROOM"].close)
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), threaded=True)
