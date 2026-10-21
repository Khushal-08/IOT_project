"""Deterministic virtual-room rules. No web server or network required."""
import math
import time
from datetime import datetime, timezone


class RoomModel:
    LIGHT_WATTS = 9
    FAN_WATTS = 60
    TARIFF = 8.0  # INR per kWh, an explicit demonstration assumption.
    EMPTY_DELAY = 10
    CAPACITY = 8

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.state = dict(light=False, fan=False, light_mode="auto", fan_mode="auto",
                          temperature=26.0, people=0, daylight=True, smoke=False, protocol=2)
        self.manual = dict(light=False, fan=False)
        self.empty_until = None
        self.empty_expired = True
        self.started = self.meter_at = clock()
        self.runtime = dict(light=0.0, fan=0.0)
        self.observed_seconds = 0.0
        self.events = []
        self.sequence = 0
        self.motion = dict(id=0, direction="enter")
        self.log("Room ready · automatic light and fan control enabled.")

    def log(self, text, level="info"):
        self.sequence += 1
        self.events.append(dict(id=self.sequence, text=text, level=level,
                               time=datetime.now(timezone.utc).isoformat()))
        self.events = self.events[-80:]

    def meter(self, now, active=True):
        elapsed = max(0.0, now - self.meter_at)
        if active:
            self.observed_seconds += elapsed
            for device in self.runtime:
                if self.state[device]:
                    self.runtime[device] += elapsed
        self.meter_at = max(self.meter_at, now)

    def output(self, device, value, reason):
        if self.state[device] != value:
            self.state[device] = value
            self.log(f"{device.title()} {'ON' if value else 'OFF'} · {reason}")

    def policy(self):
        s = self.state
        if s["smoke"]:
            self.output("light", True, "smoke alert: visibility lighting")
            self.output("fan", False, "smoke alert: fan stopped")
            return
        if s["people"] == 0:
            if self.empty_until is None:
                self.output("light", False, "room empty")
                self.output("fan", False, "room empty")
            return
        if s["light_mode"] == "auto":
            self.output("light", not s["daylight"], "occupied + " + ("daylight" if s["daylight"] else "darkness"))
        else:
            self.output("light", self.manual["light"], "manual override")
        if s["fan_mode"] == "manual":
            self.output("fan", self.manual["fan"], "manual override")
        elif s["temperature"] > 30:
            self.output("fan", True, "occupied + temperature above 30°C")
        elif s["temperature"] < 28:
            self.output("fan", False, "temperature below 28°C")

    def tick(self, active=True):
        now = self.clock()
        if active and self.empty_until is not None and now >= self.empty_until:
            self.meter(self.empty_until, active=True)
            self.empty_until = None
            self.empty_expired = True
            self.log("10-second empty-room countdown finished · " + ("smoke visibility lighting remains active." if self.state["smoke"] else "appliances shut down."))
            self.policy()
        self.meter(now, active)

    @staticmethod
    def validate(device, value):
        if not isinstance(device, str):
            raise ValueError("Unknown control.")
        if device in {"light", "fan", "daylight", "smoke"}:
            if type(value) is not bool:
                raise ValueError("State must be true or false.")
        elif device in {"light_mode", "fan_mode"}:
            if not isinstance(value, str) or value not in {"manual", "auto"}:
                raise ValueError("Choose manual or auto mode.")
        elif device == "entry":
            if not isinstance(value, str) or value not in {"enter", "exit"}:
                raise ValueError("Choose enter or exit.")
        elif device == "temperature":
            if type(value) not in {int, float} or not math.isfinite(value) or not 16 <= value <= 40:
                raise ValueError("Temperature must be between 16 and 40°C.")
        else:
            raise ValueError("Unknown control.")

    def apply(self, device, value):
        self.validate(device, value)
        self.tick()
        s = self.state
        if s["smoke"] and device in {"light", "fan", "light_mode", "fan_mode"}:
            raise ValueError("Smoke alert is active. Clear smoke before changing appliance controls.")
        if device == "entry":
            count = s["people"]
            if value == "enter" and count >= self.CAPACITY:
                raise ValueError("Room capacity is 8 people.")
            if value == "exit" and count == 0:
                raise ValueError("The room is already empty.")
            s["people"] += 1 if value == "enter" else -1
            self.motion = dict(id=self.motion["id"] + 1, direction=value)
            self.log(f"Person {'entered' if value == 'enter' else 'left'} · {s['people']} inside.")
            if value == "enter":
                if self.empty_until is not None:
                    self.log("Empty-room shutdown cancelled · someone returned.")
                self.empty_until = None
                self.empty_expired = False
            elif s["people"] == 0:
                self.empty_until = self.clock() + self.EMPTY_DELAY
                self.log("Room empty · shutting down in 10 seconds.")
        elif device in {"light", "fan"}:
            self.manual[device] = value
            s[device + "_mode"] = "manual"
            self.log(f"{device.title()} manual override selected.")
            self.output(device, value, "manual command")
            if s["people"] == 0 and value and self.empty_until is None:
                self.empty_until = self.clock() + self.EMPTY_DELAY
                self.log("Empty-room manual operation · 10-second limit.")
        else:
            if device in {"light_mode", "fan_mode"} and value == "manual":
                self.manual[device.split("_")[0]] = s[device.split("_")[0]]
            if s[device] != value:
                s[device] = value
                descriptions = {
                    "daylight": "Daylight detected." if value else "Darkness detected · night scene selected.",
                    "smoke": "SMOKE ALERT · lighting ON, fan OFF. Simulation only." if value else "Smoke cleared · normal rules restored.",
                    "temperature": f"Temperature changed to {value}°C.",
                    "light_mode": f"Light control set to {value}.",
                    "fan_mode": f"Fan control set to {value}.",
                }
                self.log(descriptions[device], "warning" if device == "smoke" and value else "info")
            # After clearing smoke, restore manual output before normal policy.
            if device == "smoke" and not value:
                for output in ("light", "fan"):
                    if s[output + "_mode"] == "manual":
                        self.output(output, self.manual[output], "manual setting restored")
        self.policy()

    def energy(self):
        light_wh = self.runtime["light"] * self.LIGHT_WATTS / 3600
        fan_wh = self.runtime["fan"] * self.FAN_WATTS / 3600
        total = (light_wh + fan_wh) / 1000
        baseline = self.observed_seconds * (self.LIGHT_WATTS + self.FAN_WATTS) / 3600
        return dict(light_wh=round(light_wh, 5), fan_wh=round(fan_wh, 5),
                    total_kwh=round(total, 7), cost=round(total * self.TARIFF, 6),
                    saved_wh=round(max(0, baseline - light_wh - fan_wh), 5),
                    light_seconds=round(self.runtime["light"], 1), fan_seconds=round(self.runtime["fan"], 1),
                    light_watts=self.LIGHT_WATTS, fan_watts=self.FAN_WATTS, tariff=self.TARIFF,
                    observed_seconds=round(self.observed_seconds, 1))
