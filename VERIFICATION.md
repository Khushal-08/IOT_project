# Verification — Smart Room v2

## Automated checks
**27 tests passed** with the project's installed Python environment (`python -m unittest discover -s tests`). JavaScript syntax validation also passed.

Coverage includes:
- Local page/assets and button/chat consistency.
- Entry-triggered dark-room lighting, daylight shutoff and occupied fan hysteresis.
- Multi-person behaviour, last-exit countdown, exact deadline expiry, re-entry cancellation and 0–8 capacity bounds.
- Manual override, manual-mode output preservation and empty-room manual timeout.
- Smoke priority, override rejection, manual-state restoration and visibility lighting during an empty-room timeout.
- Exact Wh/cost arithmetic and delayed polling across the shutdown deadline; disconnected time excluded.
- New chat vocabulary, event reasons and warning events.
- MQTT correlated confirmation, missing acknowledgement, explicit controller rejection, stale heartbeat, retained historical state and v2 telemetry validation.

Tests use an injected monotonic clock for deterministic timing and energy assertions.

## Browser checks — passed
- Night + Enter changed occupancy to 1 and switched the lamp on automatically.
- Raising the local temperature to 40°C started the automatic fan.
- A second person entered; one left; appliances stayed on with one person remaining.
- Last exit displayed the 10-second countdown. The room then reported zero people, light off and fan stopped without a further user command.
- Smoke simulation displayed smoke and the warning banner, forced light ON/fan OFF, disabled normal overrides, and restored automation after clearing.
- The chatbot returned current estimated energy/cost with the stated assumptions.
- The log displayed entry, darkness, automatic output changes and shutdown reasons.
- Mobile layout passed at a 390px viewport (375px document content width; no horizontal overflow). No browser JavaScript errors or warnings were captured during final desktop inspection.

## Actual Wokwi / MQTT v2 checks — passed
The delivered ESP32 sketch compiled successfully and ran in Wokwi with its circuit and dependencies. Flask connected to the actual virtual ESP32 through the public MQTT broker. A live API test, using the actual controller rather than a surrogate, passed:
1. Night + person entry + actual DHT22 at 32°C → automatic light and fan ON.
2. Smoke command → visibility light ON, fan OFF; clearing smoke restored the automatic fan.
3. Entry to two people, then one exit → one person remained and appliances stayed ON.
4. Last exit → countdown; immediate re-entry cancelled shutdown.
5. Another last exit → ESP32's own countdown expired and both outputs switched OFF.
6. Runtime-based energy/cost estimates increased from confirmed output intervals.

The Wokwi public internet gateway dropped its connection during testing. A restart restored connectivity and the complete checks above passed. The gateway later dropped again; local mode remains independent of this external service. Keep Wokwi running with a working gateway for the live IoT demonstration.

## Public simulation link — pending approval
The new v2 source and circuit are included in `wokwi/` and were loaded into the retained Wokwi preview. Automatic approval review rejected saving the project with Wokwi's Public privacy setting because that exposes source and circuit to everyone. No v2 public project was saved after this rejection. The previous v1 public project link is incompatible with the v2 protocol and must not be used as the updated simulator.

Publication can be completed after explicit user approval. Meanwhile, import the supplied three Wokwi files, compile and run them without publishing, using the README instructions.

## Screenshots
- `screenshots/v2-desktop.jpg`: the upgraded room, controls, energy panel and log.
- `screenshots/v2-smoke-alert.jpg`: smoke demonstration and explicit safety override.
- `screenshots/v2-mobile.jpg`: narrow-screen layout (when present).
- `screenshots/v2-wokwi.jpg`: compiled controller/circuit and v2 state (when present).

Older screenshots are retained as records of the first version; use the v2-prefixed captures for the upgraded project.


## Automatic presentation mode

Use **Play demo** for the 43-second sensor-input walkthrough. At 3s a person enters a warm daytime room (fan on, light off); at 9s darkness turns the light on; at 15s a second person enters; at 19s the temperature becomes 29°C (fan holds state); at 23s it becomes 27°C (fan off). People leave at 27s and 31s. The last exit starts the real 10-second shutdown timer. The sequence finishes at 43s.

**Emergency demo** starts with a running fan, triggers smoke at 4s, and clears it at 12s. The policy stops the fan and enables visibility lighting during smoke. Enable **Sound on** for an optional browser beep. This is a classroom simulation, not a fire-safety controller.

**Pause** freezes sensor events, while the safety countdown continues. Manual controls or chatbot changes pause a running walkthrough. **Reset · Auto** restores an empty daytime room at 32°C and both controls to Auto; session energy totals are retained. The decision panel explains each appliance state and manual override. Brightness is explicitly a day/night preset (650/20 lux), not a measured lux sensor. Temperature cooling uses scripted sensor readings, not a physical thermal model or a claimed cooling effect from a fan.

Only sensor inputs are sequenced; existing room policy chooses light and fan outputs. The backend processes scheduled timestamps in order, preserving countdowns and energy integration even after delayed polling. Automatic presentation mode is local-only; the existing Wokwi controller remains independently operated through MQTT.

Validation: 34 automated tests pass, including complete sequence, delayed polling and energy, pause/resume, reset, smoke priority, manual interruption, invalid requests and MQTT isolation. Browser walkthrough verified on the local dashboard.
