import unittest
from app import Room, create_app

class WalkthroughTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.room = Room(clock=lambda: self.now)
        self.client = create_app(self.room).test_client()
    def step(self, seconds):
        self.now += seconds
        return self.room.snapshot()
    def action(self, action):
        response = self.client.post('/api/walkthrough', json={'action':action})
        self.assertEqual(response.status_code,200)
        return response.json['state']
    def test_full_demo_uses_rules_and_real_countdown(self):
        self.action('play')
        s=self.step(3); self.assertTrue(s['fan']); self.assertFalse(s['light'])
        s=self.step(6); self.assertTrue(s['light'])
        s=self.step(14); self.assertFalse(s['fan']); self.assertEqual(s['people'],2)
        s=self.step(8); self.assertEqual(s['countdown'],10); self.assertTrue(s['light'])
        s=self.step(9); self.assertTrue(s['light'])
        s=self.step(3); self.assertFalse(s['light']); self.assertFalse(s['walkthrough']['running'])
    def test_delayed_poll_preserves_timing_and_energy(self):
        self.action('play');s=self.step(45)
        self.assertFalse(s['light']); self.assertEqual(s['people'],0)
        self.assertEqual(s['energy']['fan_seconds'],20)
        self.assertEqual(s['energy']['light_seconds'],32)
    def test_pause_resume(self):
        self.action('play');self.step(5);self.action('pause')
        self.step(20);self.assertEqual(self.room.state['daylight'],True)
        self.action('play');s=self.step(4);self.assertFalse(s['daylight'])
    def test_reset_restores_auto(self):
        self.room.command('fan',True)
        s=self.action('reset');self.assertEqual(s['fan_mode'],'auto');self.assertFalse(s['fan'])
    def test_emergency(self):
        s=self.action('emergency');self.assertTrue(s['fan'])
        s=self.step(4);self.assertTrue(s['smoke']);self.assertFalse(s['fan']);self.assertTrue(s['light'])
        s=self.step(8);self.assertFalse(s['smoke']);self.assertTrue(s['fan'])
    def test_manual_control_pauses_sequence(self):
        self.action('play');self.step(3);self.room.command('fan',False)
        s=self.step(30);self.assertFalse(s['walkthrough']['running']);self.assertFalse(s['fan'])
    def test_validation_and_mqtt(self):
        self.assertEqual(self.client.post('/api/walkthrough',json={'action':'bad'}).status_code,400)
        client=create_app(Room(mode='mqtt',start=False)).test_client()
        self.assertEqual(client.post('/api/walkthrough',json={'action':'play'}).status_code,403)
