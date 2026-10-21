"""Timed sensor-input scenarios; appliance outputs always come from RoomModel.policy."""
class DemoRunner:
    def __init__(self, room):
        self.room = room
        self.running = False
        self.elapsed = 0.0
        self.anchor = room.clock()
        self.index = 0
        self.kind = "room"
        self.label = "Ready · press Play for a 45-second walkthrough"
        self.steps = []

    def reset(self):
        r = self.room
        self.running = False
        self.elapsed = 0.0
        self.index = 0
        r.tick(active=r.online)
        r.state.update(light_mode="auto", fan_mode="auto", people=0,
                       daylight=True, temperature=32.0, smoke=False)
        r.manual.update(light=False, fan=False)
        r.empty_until = None
        r.policy()
        r.log("Demo reset · empty daytime room, both devices in Auto.")
        self.label = "Ready · warm daytime room, both controls in Auto"

    def start(self, kind="room"):
        self.reset()
        self.kind = kind
        self.steps = ([(0, [], "Empty daytime room · no appliances needed"),
            (3, [("entry", "enter")], "Person enters · heat starts fan; daylight keeps light off"),
            (9, [("daylight", False)], "It gets dark · occupied room needs light"),
            (15, [("entry", "enter")], "Second person enters · occupancy becomes two"),
            (19, [("temperature", 29.0)], "Cooling to 29°C · fan holds its previous state"),
            (23, [("temperature", 27.0)], "Cooling below 28°C · fan stops automatically"),
            (27, [("entry", "exit")], "One person leaves · room still occupied"),
            (31, [("entry", "exit")], "Last person leaves · real 10-second shutdown countdown"),
            (43, [], "Demo complete · empty room, appliances off")]
            if kind == "room" else [
            (0, [("entry", "enter")], "Warm occupied room · fan running"),
            (4, [("smoke", True)], "Smoke detected · fan cut off, visibility light and alarm on"),
            (12, [("smoke", False)], "Smoke clears · normal automation resumes"),
            (17, [], "Emergency demonstration complete")])
        self.anchor = self.room.clock()
        self.running = True
        self.advance()

    def advance(self):
        if not self.running:
            return
        r = self.room
        now = r.clock()
        target = self.elapsed + max(0, now - self.anchor)
        original_clock = r.clock
        try:
            while self.index < len(self.steps) and self.steps[self.index][0] <= target:
                at, inputs, label = self.steps[self.index]
                r.clock = lambda at=at: self.anchor + at - self.elapsed
                r.tick(active=r.online)
                for device, value in inputs:
                    r.apply(device, value)
                self.label = label
                r.log("Demo · " + label)
                self.index += 1
        finally:
            r.clock = original_clock
        self.elapsed = target
        self.anchor = now
        if self.index == len(self.steps):
            self.running = False

    def action(self, action):
        if action in {"play", "emergency"}:
            if action == "play" and not self.running and self.index and self.index < len(self.steps):
                self.anchor = self.room.clock()
                self.running = True
            else:
                self.start("emergency" if action == "emergency" else "room")
        elif action == "pause":
            self.advance()
            self.running = False
            self.room.log("Demo paused · sensor sequence paused; safety countdown remains live.")
        elif action == "reset":
            self.reset()
        else:
            raise ValueError("Choose play, pause, reset or emergency.")

    def snapshot(self):
        return dict(running=self.running, elapsed=round(self.elapsed, 1),
                    duration=43 if self.kind == "room" else 17, label=self.label,
                    step=self.index, kind=self.kind)


def decisions(s, countdown):
    if s["smoke"]:
        return dict(light="Smoke alert → visibility light ON", fan="Smoke alert → fan stopped", alarm="SMOKE ALERT · evacuate simulated room")
    if not s["people"]:
        reason = "Room empty → shutdown in %ss" % countdown if countdown is not None else "Room empty → appliance OFF"
        return dict(light=reason, fan=reason, alarm="Smoke sensor clear")
    light = "Manual override → light " + ("ON" if s["light"] else "OFF") if s["light_mode"] == "manual" else ("Occupied + daylight → light OFF" if s["daylight"] else "Occupied + darkness → light ON")
    fan = "Manual override → fan " + ("ON" if s["fan"] else "OFF") if s["fan_mode"] == "manual" else ("Occupied + above 30°C → fan ON" if s["temperature"] > 30 else "Below 28°C → fan OFF" if s["temperature"] < 28 else "28–30°C → hold previous fan state")
    return dict(light=light, fan=fan, alarm="Smoke sensor clear")
