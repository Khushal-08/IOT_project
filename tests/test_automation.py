import unittest

from app import Room, create_app


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.room = Room(clock=self.clock)
        self.client = create_app(self.room).test_client()

    def control(self, device, value):
        result = self.client.post('/api/control', json=dict(device=device, value=value))
        self.assertEqual(result.status_code, 200, result.json)
        return result.json['state']

    def state(self):
        return self.client.get('/api/state').json

    def test_dark_empty_room_stays_off_until_entry(self):
        self.assertFalse(self.control('daylight', False)['light'])
        state = self.control('entry', 'enter')
        self.assertEqual(state['people'], 1)
        self.assertTrue(state['light'])
        self.assertEqual(state['light_mode'], 'auto')

    def test_daylight_switches_automatic_light_off(self):
        self.control('daylight', False)
        self.control('entry', 'enter')
        self.assertFalse(self.control('daylight', True)['light'])

    def test_occupied_fan_and_last_exit_countdown(self):
        self.control('temperature', 32)
        self.assertFalse(self.state()['fan'])
        self.control('entry', 'enter')
        self.assertTrue(self.state()['fan'])
        self.control('entry', 'enter')
        self.control('entry', 'exit')
        self.assertIsNone(self.state()['countdown'])
        state = self.control('entry', 'exit')
        self.assertEqual(state['countdown'], 10)
        self.clock.advance(9)
        self.assertTrue(self.state()['fan'])
        self.assertEqual(self.state()['countdown'], 1)
        self.clock.advance(1)
        self.assertFalse(self.state()['fan'])
        self.assertIsNone(self.state()['countdown'])

    def test_reentry_cancels_shutdown(self):
        self.control('daylight', False)
        self.control('entry', 'enter')
        self.control('entry', 'exit')
        self.clock.advance(6)
        self.control('entry', 'enter')
        self.clock.advance(20)
        self.assertTrue(self.state()['light'])
        self.assertIsNone(self.state()['countdown'])

    def test_people_bounds_and_motion(self):
        result = self.client.post('/api/control', json=dict(device='entry', value='exit'))
        self.assertEqual(result.status_code, 400)
        for _ in range(8):
            self.control('entry', 'enter')
        self.assertEqual(self.state()['motion']['id'], 8)
        result = self.client.post('/api/control', json=dict(device='entry', value='enter'))
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.state()['people'], 8)

    def test_manual_light_override_then_auto_restore(self):
        self.control('entry', 'enter')
        self.control('daylight', False)
        self.control('light', False)
        self.assertFalse(self.state()['light'])
        self.assertEqual(self.state()['light_mode'], 'manual')
        self.assertTrue(self.control('light_mode', 'auto')['light'])

    def test_manual_empty_room_still_times_out(self):
        self.control('light', True)
        self.clock.advance(10)
        self.assertFalse(self.state()['light'])

    def test_selecting_manual_preserves_the_current_output(self):
        self.control('daylight', False)
        self.control('entry', 'enter')
        self.assertTrue(self.control('light_mode', 'manual')['light'])
        self.assertTrue(self.control('daylight', True)['light'])

    def test_smoke_priority_and_manual_restore(self):
        self.control('entry', 'enter')
        self.control('light', False)
        self.control('fan', True)
        state = self.control('smoke', True)
        self.assertTrue(state['light'])
        self.assertFalse(state['fan'])
        result = self.client.post('/api/control', json=dict(device='fan', value=True))
        self.assertEqual(result.status_code, 400)
        state = self.control('smoke', False)
        self.assertFalse(state['light'])
        self.assertTrue(state['fan'])

    def test_smoke_keeps_visibility_light_even_after_empty_timeout(self):
        self.control('entry', 'enter')
        self.control('smoke', True)
        self.control('entry', 'exit')
        self.clock.advance(12)
        self.assertTrue(self.state()['light'])
        self.assertFalse(self.control('smoke', False)['light'])

    def test_exact_energy_and_shutdown_without_browser_polling(self):
        self.control('daylight', False)
        self.control('temperature', 32)
        self.control('entry', 'enter')
        self.clock.advance(60)
        e = self.state()['energy']
        self.assertAlmostEqual(e['light_wh'], .15)
        self.assertAlmostEqual(e['fan_wh'], 1)
        self.assertAlmostEqual(e['cost'], .00115 * 8)
        self.control('entry', 'exit')
        self.clock.advance(100)  # Must count only the 10-second grace period.
        e = self.state()['energy']
        self.assertAlmostEqual(e['light_seconds'], 70)
        self.assertAlmostEqual(e['fan_seconds'], 70)

    def test_disconnected_time_not_counted_as_measured_runtime(self):
        self.control('light', True)
        self.clock.advance(3)
        self.client.post('/api/demo', json={'online': False})
        self.clock.advance(30)
        self.state()
        self.client.post('/api/demo', json={'online': True})
        self.assertAlmostEqual(self.state()['energy']['light_seconds'], 3)

    def test_new_chat_commands_and_activity(self):
        for text in ['night mode', 'enter room', 'fan auto', 'light auto', 'energy usage', 'people', 'simulate smoke', 'clear smoke', 'leave room']:
            result = self.client.post('/api/chat', json={'message': text})
            self.assertEqual(result.status_code, 200, (text, result.json))
            self.assertNotIn('Try', result.json['message'])
        events = self.state()['events']
        self.assertTrue(any('darkness' in item['text'].lower() for item in events))
        self.assertTrue(any(item['level'] == 'warning' for item in events))


if __name__ == '__main__':
    unittest.main()
