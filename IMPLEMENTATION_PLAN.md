# Occupancy-Based Smart Room Automation with Chatbot and Energy Monitoring

## Implementation scope
Keep the existing Flask, plain JavaScript and MQTT architecture, with a white rounded interface. Extend the existing room rather than adding separate unrelated screens.

1. **Room model:** explicit people count (0–8), day/night input, light and fan Auto/Manual modes, smoke flag, monotonic 10-second empty-room timer, capped event log and session energy estimator.
2. **Automation:** occupied + dark enables automatic lighting. Occupied + temperature above 30°C enables the automatic fan; below 28°C disables it. Intermediate temperatures preserve fan state. Last exit starts a 10-second grace period. Re-entry cancels shutdown. Manual power in an empty room is also limited to 10 seconds.
3. **Safety demonstration:** smoke forces the visibility light on and the fan off, and blocks appliance overrides until cleared. This illustrative response is not a real fire-protection system. Normal selected modes resume after clearing smoke. Smoke visibility lighting takes priority over empty-room shutdown.
4. **Visual interaction:** door opens during entry/exit; an animated person walks through the doorway; static occupants and the numeric count show occupancy. Night changes the window and room, with a moon indicator. Smoke animates in the room and activates an explicit warning banner.
5. **Controls and chat:** Enter/Leave, Day/Night, separate Auto/Manual controls, Simulate/Clear smoke, temperature slider in local mode, expanded fixed command vocabulary. Both input paths reach the same backend rules.
6. **Energy and activity:** derive runtime from confirmed output state and elapsed connected time. Assume light 9 W, fan 60 W, tariff ₹8/kWh. Show estimated Wh, cost, device runtime and comparison with both devices continuously on. Log sensor changes and the reason behind automatic changes. Keep everything in memory.
7. **IoT protocol v2:** ESP32 is authoritative in MQTT mode. Dashboard commands carry IDs; telemetry returns the applied state or explicit rejection. Controller independently handles timers, smoke priority and sensor rules. Wokwi buttons emulate entry, exit, day/night and smoke inputs; the DHT22 supplies temperature.
8. **Verification and delivery:** deterministic fake-clock tests for countdown, re-entry, smoke precedence, exact energy integration, capacity and manual overrides; browser verification of animations and controls; compile/run the ESP32 simulation; refresh source ZIP, setup guide, screenshots and report.

## Demo sequence
Night → Enter → light automatically ON → temperature 32°C → fan automatically ON → second person enters → first person leaves (devices remain ON) → last person leaves → observe countdown → re-enter to cancel → leave and wait for shutdown → simulate smoke → observe warning/light/fan → clear smoke → inspect energy and activity.

Entry/exit and day/night are explicit simulated sensor events. A single PIR signal is not claimed to provide an accurate people count. Energy is a runtime estimate, not a meter reading. Events, energy and people state reset with the local server/controller session.


## Automatic presentation mode

Use **Play demo** for the 43-second sensor-input walkthrough. At 3s a person enters a warm daytime room (fan on, light off); at 9s darkness turns the light on; at 15s a second person enters; at 19s the temperature becomes 29°C (fan holds state); at 23s it becomes 27°C (fan off). People leave at 27s and 31s. The last exit starts the real 10-second shutdown timer. The sequence finishes at 43s.

**Emergency demo** starts with a running fan, triggers smoke at 4s, and clears it at 12s. The policy stops the fan and enables visibility lighting during smoke. Enable **Sound on** for an optional browser beep. This is a classroom simulation, not a fire-safety controller.

**Pause** freezes sensor events, while the safety countdown continues. Manual controls or chatbot changes pause a running walkthrough. **Reset · Auto** restores an empty daytime room at 32°C and both controls to Auto; session energy totals are retained. The decision panel explains each appliance state and manual override. Brightness is explicitly a day/night preset (650/20 lux), not a measured lux sensor. Temperature cooling uses scripted sensor readings, not a physical thermal model or a claimed cooling effect from a fan.

Only sensor inputs are sequenced; existing room policy chooses light and fan outputs. The backend processes scheduled timestamps in order, preserving countdowns and energy integration even after delayed polling. Automatic presentation mode is local-only; the existing Wokwi controller remains independently operated through MQTT.

Validation: 34 automated tests pass, including complete sequence, delayed polling and energy, pause/resume, reset, smoke priority, manual interruption, invalid requests and MQTT isolation. Browser walkthrough verified on the local dashboard.
