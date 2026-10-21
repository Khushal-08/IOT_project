# Occupancy-Based Smart Room Automation

One illustrated room, sensor-driven automation, a small rule-based chatbot, smoke-alert simulation, estimated energy use and an explainable activity log. Software only; no AI API or physical devices needed.

## Run locally

On Windows, double-click **start.bat**, then open **http://127.0.0.1:5000/**. Keep the terminal running. The launcher uses standard Python 3.10+ or the bundled Codex Python runtime if available. First-time setup requires internet; local simulation works offline after dependencies are installed.

Manual setup from this folder:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

On macOS/Linux, use `python3` for setup and `.venv/bin/python` for the last two commands.

## Demonstration

1. Select **Night**. The window and room become dark; an empty room stays unlit.
2. Click **Enter room**. The door opens, a person walks in, and the automatic light switches on.
3. Open **Local simulator** and increase temperature above 30°C. The automatic fan starts.
4. Enter a second person, then let one leave. Appliances stay on while somebody is inside.
5. Let the last person leave. A **10-second countdown** appears. Re-enter to cancel it, or wait for the light and fan to stop.
6. Select **Day** while somebody is inside: the automatic light switches off in daylight.
7. Click **Simulate smoke**. A smoke effect and warning appear. The demonstration's visibility light turns on and the fan stops. Appliance overrides are disabled until **Clear smoke**.
8. Read **energy estimates** and **activity log** to explain the decisions.

## Rules and priorities

| Priority / condition | Result |
| --- | --- |
| Smoke active | Light ON for visibility, fan OFF. Overrides blocked. |
| Last person leaves | Hold outputs for a 10-second grace period; then turn both off. |
| Somebody returns during countdown | Cancel shutdown and re-evaluate current modes/sensors. |
| Occupied + light Auto | Light ON at night; OFF in daylight. |
| Occupied + fan Auto | ON above 30°C; OFF below 28°C; keep previous state from 28–30°C inclusive. |
| Manual light/fan command | Set that appliance to Manual. |
| Manual ON in empty room | Allowed for at most 10 seconds. |
| Select Auto | Return that appliance to sensor rules. |

A smoke alert takes priority over empty-room shutdown, so visibility lighting stays on during the alert. Clearing smoke restores normal selected modes. Selecting Manual preserves the current output until the next manual command. People count is bounded to **0–8**; the picture shows up to four representative occupants, while the badge shows the full count.

Entry/exit controls emulate separate door-sensor events. Day/Night is an explicit simulated ambient-light input, not a claim that a real light sensor is connected. A single PIR sensor is not claimed to give accurate people counts. The smoke response is a classroom illustration, not a real fire-protection system.

## Chat commands

`enter room`, `leave room`, `night mode`, `day mode`, `people`, `light on`, `light off`, `fan on`, `fan off`, `light auto`, `light manual`, `fan auto`, `fan manual`, `temperature`, `simulate smoke`, `clear smoke`, `energy usage`, `status`.

The chatbot matches supported words and phrases. Unknown commands return help. It does not call an AI service. Device states change only after backend/controller confirmation.

## Energy estimates

Assumptions are shown on screen: **9 W light**, **60 W fan**, **₹8/kWh**. Runtime is integrated from confirmed output state and elapsed connected time. Wh = watts × seconds / 3600; estimated cost = kWh × tariff. “Wh avoided” compares with both devices running continuously during the same connected session, not with a measured household baseline. Offline time is excluded; unobserved network transitions can limit MQTT estimates. No physical energy meter is used.

People, events and energy are held in memory. Local-server restart resets the local room and estimates. Page refresh clears the conversation but keeps backend session state. MQTT device state resets when ESP32 restarts; the backend's energy/log session resets when Flask restarts. The log retains the latest 80 events and displays the newest 25.

## Wokwi and MQTT v2

Use the v2 simulation files in **wokwi/**. The older v1 Wokwi project is incompatible with this upgraded telemetry protocol. The current saved v2 project link is listed in **VERIFICATION.md** when available.

To recreate the circuit: open https://wokwi.com/projects/new/esp32, replace `sketch.ino` and `diagram.json`, and add the supplied `libraries.txt`. The libraries are PubSubClient, DHT sensor library for ESPx and ArduinoJson.

Virtual components:
- ESP32 + DHT22 on GPIO15.
- Yellow light LED GPIO18, blue fan indicator GPIO19, red smoke-alert indicator GPIO23.
- Buttons: GPIO32 ENTER, GPIO33 EXIT, GPIO25 DAY/NIGHT, GPIO26 SMOKE/CLEAR. They emulate the corresponding sensor inputs.
- Click DHT22 to change temperature; press each button briefly to trigger its event.

Start the controller in Wokwi. Then run **start-wokwi.bat**, or use:

```powershell
$env:HOME_MODE = "mqtt"
$env:PORT = "5001"
$env:MQTT_HOST = "broker.hivemq.com"
$env:MQTT_PORT = "1883"
$env:MQTT_TOPIC = "student/smart-home/room-7e24b1c903-v2"
.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:5001/**. Wokwi and Flask must use identical broker/topic settings. Choose a unique topic for your own group and change both sides; copies on the same topic control the same virtual room. Local 5000 and MQTT 5001 may run together with independent room state. In MQTT mode, use Wokwi's DHT22 for temperature; the other dashboard controls send real MQTT commands to ESP32.

The ESP32 independently owns automation and timers. It publishes v2 telemetry every second and echoes command IDs only after applying or rejecting a command. Rejections carry an explicit error. Commands are not retained. Flask marks stale devices offline after 10 seconds without live telemetry; retained historical state does not prove a device is online.

Public-broker traffic is not private. Use only virtual, non-sensitive classroom data. Both processes make outgoing broker connections; Flask stays on localhost. If Wokwi's gateway fails, save/restart the simulation and check connectivity. Some school networks block MQTT port 1883.

Optional backend settings: `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_TLS=1`, `MQTT_PORT`, `MQTT_TOPIC`, `PORT`. Match any broker/authentication/TLS changes in the ESP32 source too; the supplied sketch uses public unauthenticated TCP.

## Files and checks

- `app.py`: Flask API and confirmed-state MQTT bridge.
- `room_model.py`: local rules, occupancy/countdown, event log and energy integration.
- `templates/index.html`, `static/`: responsive room, chat, controls and insights.
- `wokwi/`: independent ESP32 controller, circuit and libraries.
- `IMPLEMENTATION_PLAN.md`: feature implementation and presentation sequence.
- `PROJECT_REPORT.md`, `VERIFICATION.md`: report and actual verification evidence.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests use an injectable clock to verify 10-second timers and exact energy integration without waiting in real time. See VERIFICATION.md for browser and IoT checks actually performed.


## Automatic presentation mode

Use **Play demo** for the 43-second sensor-input walkthrough. At 3s a person enters a warm daytime room (fan on, light off); at 9s darkness turns the light on; at 15s a second person enters; at 19s the temperature becomes 29°C (fan holds state); at 23s it becomes 27°C (fan off). People leave at 27s and 31s. The last exit starts the real 10-second shutdown timer. The sequence finishes at 43s.

**Emergency demo** starts with a running fan, triggers smoke at 4s, and clears it at 12s. The policy stops the fan and enables visibility lighting during smoke. Enable **Sound on** for an optional browser beep. This is a classroom simulation, not a fire-safety controller.

**Pause** freezes sensor events, while the safety countdown continues. Manual controls or chatbot changes pause a running walkthrough. **Reset · Auto** restores an empty daytime room at 32°C and both controls to Auto; session energy totals are retained. The decision panel explains each appliance state and manual override. Brightness is explicitly a day/night preset (650/20 lux), not a measured lux sensor. Temperature cooling uses scripted sensor readings, not a physical thermal model or a claimed cooling effect from a fan.

Only sensor inputs are sequenced; existing room policy chooses light and fan outputs. The backend processes scheduled timestamps in order, preserving countdowns and energy integration even after delayed polling. Automatic presentation mode is local-only; the existing Wokwi controller remains independently operated through MQTT.

Validation: 34 automated tests pass, including complete sequence, delayed polling and energy, pause/resume, reset, smoke priority, manual interruption, invalid requests and MQTT isolation. Browser walkthrough verified on the local dashboard.
