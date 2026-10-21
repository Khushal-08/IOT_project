"""Behaviour tests: no internet or MQTT broker needed."""
import json
import threading
import time
import unittest
from unittest.mock import patch

from app import Room, create_app, parse_command


class RoomTests(unittest.TestCase):
    def setUp(self):
        self.room = Room("demo", clock=lambda: 1000.0)
        self.client = create_app(self.room).test_client()

    def post(self, path, **data):
        return self.client.post(path, json=data)

    def test_page_and_static_assets(self):
        for url in ["/", "/static/app.js", "/static/style.css"]:
            with self.client.get(url) as response:
                self.assertEqual(response.status_code, 200)

    def test_chat_controls_same_state_as_buttons(self):
        result = self.post("/api/chat", message="Switch on the light!")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json["state"]["light"])
        self.post("/api/control", device="light", value=False)
        self.assertFalse(self.client.get("/api/state").json["light"])

    def test_thresholds_and_hysteresis(self):
        self.post("/api/control", device="entry", value="enter")
        self.post("/api/control", device="fan_mode", value="auto")
        for temperature, expected in [(30, False), (30.5, True), (30, True),
                                      (29, True), (28, True), (27.5, False), (29, False)]:
            with self.subTest(temperature=temperature):
                result = self.post("/api/demo", temperature=temperature)
                self.assertEqual(result.json["state"]["fan"], expected)

    def test_manual_command_overrides_auto(self):
        self.post("/api/control", device="entry", value="enter")
        self.post("/api/demo", temperature=35)
        self.post("/api/control", device="fan_mode", value="auto")
        result = self.post("/api/chat", message="fan off")
        self.assertFalse(result.json["state"]["fan"])
        self.assertEqual(result.json["state"]["fan_mode"], "manual")
        self.post("/api/demo", temperature=36)
        self.assertFalse(self.client.get("/api/state").json["fan"])

    def test_unknown_command_does_not_change_outputs(self):
        before = self.room.snapshot()
        result = self.post("/api/chat", message="Tell me a joke")
        self.assertIn("Try", result.json["message"])
        self.assertEqual(before, self.room.snapshot())
        for message in ["light on off", "light and fan on"]:
            self.assertEqual(parse_command(message), (None, None))

    def test_temperature_and_status(self):
        self.post("/api/demo", temperature=32.5)
        result = self.post("/api/chat", message="What is the temperature?")
        self.assertIn("32.5", result.json["message"])
        self.assertIn("Light: off", self.post("/api/chat", message="status").json["message"])

    def test_disconnect_reconnect(self):
        self.post("/api/demo", online=False)
        self.assertIsNone(self.client.get("/api/state").json["temperature"])
        for path, data in [("/api/chat", {"message": "light on"}),
                           ("/api/control", {"device": "fan", "value": True}),
                           ("/api/chat", {"message": "temperature"})]:
            self.assertEqual(self.client.post(path, json=data).status_code, 503)
        self.assertFalse(self.room.state["light"])
        self.post("/api/demo", online=True)
        self.assertEqual(self.post("/api/chat", message="light on").status_code, 200)

    def test_invalid_input(self):
        invalid = [("/api/control", {"device": "light", "value": "on"}),
                   ("/api/control", {"device": [], "value": True}),
                   ("/api/control", {"device": "fan_mode", "value": []}),
                   ("/api/control", {"device": "heater", "value": True}),
                   ("/api/demo", {"temperature": 99}),
                   ("/api/demo", {"temperature": "hot"}),
                   ("/api/demo", {"temperature": True}),
                   ("/api/demo", {"online": "false"}),
                   ("/api/chat", {"message": ""}),
                   ("/api/chat", {"message": 123}),
                   ("/api/chat", {"message": "a" * 201})]
        for path, data in invalid:
            with self.subTest(data=data):
                self.assertEqual(self.client.post(path, json=data).status_code, 400)
        self.assertEqual(self.client.post("/api/chat", json=[]).status_code, 400)


class MqttTests(unittest.TestCase):
    def setUp(self):
        self.room = Room("mqtt", start=False)
        self.room.online = True
        self.room.broker_connected = True
        self.room.last_seen = time.monotonic()

    def test_mqtt_hides_demo_controls_api(self):
        client = create_app(self.room).test_client()
        self.assertEqual(client.post("/api/demo", json={"temperature": 26}).status_code, 403)

    def test_missing_heartbeat_goes_offline(self):
        self.room.last_seen -= 11
        self.assertFalse(self.room.snapshot()["online"])
        with self.assertRaises(ConnectionError):
            self.room.command("light", True)

    def test_confirmation_is_required_and_correlated(self):
        class Device:
            def publish(device, topic, payload, **kwargs):
                command = json.loads(payload)
                self.assertFalse(kwargs["retain"])
                def confirm():
                    with self.room.condition:
                        self.room.state["light"] = command["value"]
                        self.room.last_id = command["id"]
                        self.room.condition.notify_all()
                threading.Timer(.02, confirm).start()
                return type("Result", (), {"rc": 0})()
        self.room.client = Device()
        self.assertTrue(self.room.command("light", True)["light"])

    def test_published_without_ack_is_not_success(self):
        self.room.client = type("Device", (), {"publish": lambda *a, **k: type("Result", (), {"rc": 0})()})()
        with patch.object(self.room.condition, "wait_for", return_value=False):
            with self.assertRaisesRegex(ConnectionError, "did not confirm"):
                self.room.command("light", True)
        self.assertFalse(self.room.state["light"])

    def test_device_rejection_is_not_reported_as_success(self):
        class Device:
            def publish(device, topic, payload, **kwargs):
                command = json.loads(payload)
                def reject():
                    with self.room.condition:
                        self.room.last_id = command['id']
                        self.room.last_error = 'Controller rejected this command.'
                        self.room.condition.notify_all()
                threading.Timer(.01, reject).start()
                return type('Result', (), {'rc': 0})()
        self.room.client = Device()
        with self.assertRaisesRegex(ValueError, 'Controller rejected'):
            self.room.command('light', True)
        self.assertFalse(self.room.state['light'])

    def test_v2_telemetry_validation_and_retained_state(self):
        with patch('paho.mqtt.client.Client'):
            room = Room('mqtt')
        valid = dict(room.state, people=2, light=True, countdown=None, id='sample')
        def receive(payload, retained=False):
            message = type('Message', (), dict(topic=room.topic + '/state', payload=json.dumps(payload).encode(), retain=retained))()
            room.client.on_message(None, None, message)
        receive(valid, retained=True)
        self.assertFalse(room.online)
        for bad in [dict(valid, people=-1), dict(valid, people=9), dict(valid, temperature=True), dict(valid, protocol=1), dict(valid, countdown=11)]:
            receive(bad)
            self.assertFalse(room.online)
        receive(valid)
        self.assertTrue(room.snapshot()['online'])
        self.assertEqual(room.state['people'], 2)
        self.assertTrue(room.state['light'])
        room.close()


if __name__ == "__main__":
    unittest.main()
