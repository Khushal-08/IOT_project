# Occupancy-Based Smart Room Automation with Chatbot and Energy Monitoring

## Problem statement
A room wastes electricity when appliances remain on after people leave or when lighting runs despite sufficient daylight. Users also need an understandable way to override appliances and see why automatic actions happen. This project demonstrates those behaviours using a virtual room rather than physical hardware.

## Objectives
- Track explicit entry/exit events and maintain a bounded people count.
- Automatically operate a light using occupancy and a day/night input.
- Automatically operate a fan using occupancy and temperature.
- Stop unnecessary operation after a 10-second empty-room grace period.
- Demonstrate a smoke-triggered priority response and clear/reset workflow.
- Provide fixed text commands, runtime-based energy estimates and an explainable event log.

## Implementation
The interface uses HTML, CSS, SVG and plain JavaScript. A Flask backend provides commands, local simulation, estimates and logs. An ESP32 project in Wokwi supplies an independent implementation of the same control rules in MQTT mode. Paho MQTT bridges Flask to the controller; the controller echoes command IDs with confirmed state or an explicit rejection.

The circuit contains an ESP32, DHT22, yellow light indicator, blue fan indicator and red smoke-alert indicator. Four pushbuttons emulate entry, exit, day/night and smoke/clear sensor inputs. The light/fan indicators represent switching states; no real appliance motor is driven. Entry and exit are separate events, rather than an unsupported claim of exact counting from a single PIR signal.

## Automation algorithm
1. Smoke alert has the highest priority: turn visibility lighting on, stop the fan and block normal appliance overrides until cleared. This is an illustrative classroom policy, not a real fire-protection system.
2. On entry, increment occupancy (maximum 8), cancel any pending empty-room timer, and evaluate selected appliance modes.
3. In Auto, turn the light on only when the room is occupied and the day/night input indicates darkness.
4. In Auto, turn the fan on above 30°C and off below 28°C while occupied. Preserve its state between the two thresholds to avoid repeated switching.
5. On exit, decrement occupancy without allowing negative counts. If someone remains, keep normal rules active. If the last person leaves, start a 10-second grace period.
6. If a person returns before expiry, cancel the timer. Otherwise turn both appliances off. Smoke visibility lighting retains priority.
7. Manual power commands select Manual mode for that appliance. Manual operation in an empty room is limited to 10 seconds. Selecting Auto resumes sensor rules.

## User interface
One white, rounded dashboard remains centred on the illustrated room. A door opens and a person walks in/out when occupancy changes. People, daylight, lamp illumination, fan rotation, smoke and warnings reflect confirmed room state. Entry/exit and day/night controls sit beside the appliance controls; the compact chatbot remains alongside the room. Energy estimates and activity history appear below. The page stacks on mobile and honours reduced-motion settings.

## Energy calculations
Assume a 9 W light, a 60 W fan and ₹8/kWh. For each confirmed ON interval, energy in Wh = watts × seconds / 3600. Estimated cost = kWh × assumed tariff. A clearly labelled comparison shows energy avoided versus both appliances running continuously during the same connected session. These are estimates, not meter readings or measured household savings. Offline/unobserved transitions limit MQTT precision.

## Demonstration
Night → Enter room → automatic light ON → increase temperature → fan ON → enter another person → let one leave → observe appliances still ON → last person leaves → countdown → re-enter to cancel → leave and wait for automatic shutdown → simulate smoke → warning/light/fan priority → clear smoke → inspect activity reasons and energy estimates.

The local demo uses browser controls to emulate inputs. MQTT mode sends those input commands to the actual simulated ESP32; temperature changes are made using Wokwi's DHT22.

## Scope and limitations
One room, up to eight counted people, fixed commands, in-memory session history and no authentication. The drawing shows four representative occupants while the numeric badge shows the full count. No physical sensing, measured power, unrestricted AI conversation or real-world safety certification is claimed. Internet is needed only for MQTT/Wokwi mode and first-time dependency setup. Local simulation works independently after setup. See VERIFICATION.md for checks actually performed and the pending public-project publication approval.


## Automatic presentation mode

Use **Play demo** for the 43-second sensor-input walkthrough. At 3s a person enters a warm daytime room (fan on, light off); at 9s darkness turns the light on; at 15s a second person enters; at 19s the temperature becomes 29°C (fan holds state); at 23s it becomes 27°C (fan off). People leave at 27s and 31s. The last exit starts the real 10-second shutdown timer. The sequence finishes at 43s.

**Emergency demo** starts with a running fan, triggers smoke at 4s, and clears it at 12s. The policy stops the fan and enables visibility lighting during smoke. Enable **Sound on** for an optional browser beep. This is a classroom simulation, not a fire-safety controller.

**Pause** freezes sensor events, while the safety countdown continues. Manual controls or chatbot changes pause a running walkthrough. **Reset · Auto** restores an empty daytime room at 32°C and both controls to Auto; session energy totals are retained. The decision panel explains each appliance state and manual override. Brightness is explicitly a day/night preset (650/20 lux), not a measured lux sensor. Temperature cooling uses scripted sensor readings, not a physical thermal model or a claimed cooling effect from a fan.

Only sensor inputs are sequenced; existing room policy chooses light and fan outputs. The backend processes scheduled timestamps in order, preserving countdowns and energy integration even after delayed polling. Automatic presentation mode is local-only; the existing Wokwi controller remains independently operated through MQTT.

Validation: 34 automated tests pass, including complete sequence, delayed polling and energy, pause/resume, reset, smoke priority, manual interruption, invalid requests and MQTT isolation. Browser walkthrough verified on the local dashboard.
