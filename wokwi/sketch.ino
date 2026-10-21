// Smart Room v2: occupancy, daylight, smoke and a 10-second empty-room timer.
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHTesp.h>
#include <ArduinoJson.h>

const char* BROKER = "broker.hivemq.com";
const int BROKER_PORT = 1883;
const char* ROOM_TOPIC = "student/smart-home/room-7e24b1c903-v2";
const int LIGHT_PIN = 18, FAN_PIN = 19, SENSOR_PIN = 15, ALARM_PIN = 23;
const int BUTTON_PINS[] = {32, 33, 25, 26}; // Enter, exit, day/night, smoke/clear.
WiFiClient wifi;
PubSubClient mqtt(wifi);
DHTesp sensor;
bool lightOn = false, fanOn = false, lightAuto = true, fanAuto = true;
bool manualLight = false, manualFan = false, daylight = true, smoke = false;
bool emptyPending = false;
int people = 0;
float temperature = 26.0;
unsigned long emptySince = 0, lastReading = 0, lastPublish = 0, lastReconnect = 0;
bool rawButton[] = {HIGH, HIGH, HIGH, HIGH};
bool stableButton[] = {HIGH, HIGH, HIGH, HIGH};
unsigned long changedAt[] = {0, 0, 0, 0};
String lastCommandId = "", lastError = "";
String stateTopic, commandTopic, availabilityTopic;

void applyOutputs() {
  if (emptyPending && millis() - emptySince >= 10000UL) emptyPending = false;
  if (smoke) {
    lightOn = true;
    fanOn = false;
  } else if (people == 0) {
    if (!emptyPending) { lightOn = false; fanOn = false; }
  } else {
    lightOn = lightAuto ? !daylight : manualLight;
    if (!fanAuto) fanOn = manualFan;
    else if (temperature > 30) fanOn = true;
    else if (temperature < 28) fanOn = false;
  }
  digitalWrite(LIGHT_PIN, lightOn);
  digitalWrite(FAN_PIN, fanOn);
  digitalWrite(ALARM_PIN, smoke);
}

void publishState() {
  JsonDocument state;
  state["protocol"] = 2;
  state["light"] = lightOn;
  state["fan"] = fanOn;
  state["light_mode"] = lightAuto ? "auto" : "manual";
  state["fan_mode"] = fanAuto ? "auto" : "manual";
  state["temperature"] = temperature;
  state["people"] = people;
  state["daylight"] = daylight;
  state["smoke"] = smoke;
  if (emptyPending) {
    unsigned long elapsed = millis() - emptySince;
    state["countdown"] = elapsed >= 10000UL ? 0 : (10000UL - elapsed + 999UL) / 1000UL;
  } else state["countdown"] = nullptr;
  state["id"] = lastCommandId;
  state["error"] = lastError;
  char buffer[768];
  serializeJson(state, buffer, sizeof(buffer));
  if (mqtt.connected()) mqtt.publish(stateTopic.c_str(), buffer, false);
  Serial.println(buffer);
}

bool occupancy(bool enter) {
  if (enter && people >= 8) { lastError = "Room capacity is 8 people."; return false; }
  if (!enter && people == 0) { lastError = "The room is already empty."; return false; }
  people += enter ? 1 : -1;
  if (enter) emptyPending = false;
  else if (people == 0) { emptyPending = true; emptySince = millis(); }
  return true;
}

bool changeControl(String device, JsonVariantConst value) {
  if (smoke && (device == "light" || device == "fan" || device == "light_mode" || device == "fan_mode")) {
    lastError = "Smoke alert is active. Clear smoke first.";
    return false;
  }
  if (device == "entry" && value.is<const char*>()) {
    String direction = value.as<String>();
    if (direction != "enter" && direction != "exit") return false;
    return occupancy(direction == "enter");
  }
  if ((device == "light" || device == "fan") && value.is<bool>()) {
    bool on = value.as<bool>();
    if (device == "light") { lightAuto = false; manualLight = on; lightOn = on; }
    else { fanAuto = false; manualFan = on; fanOn = on; }
    if (people == 0 && on && !emptyPending) { emptyPending = true; emptySince = millis(); }
    return true;
  }
  if ((device == "light_mode" || device == "fan_mode") && value.is<const char*>()) {
    String mode = value.as<String>();
    if (mode != "auto" && mode != "manual") return false;
    if (device == "light_mode") { if (mode == "manual") manualLight = lightOn; lightAuto = mode == "auto"; }
    else { if (mode == "manual") manualFan = fanOn; fanAuto = mode == "auto"; }
    return true;
  }
  if (device == "daylight" && value.is<bool>()) { daylight = value.as<bool>(); return true; }
  if (device == "smoke" && value.is<bool>()) {
    smoke = value.as<bool>();
    if (!smoke) { if (!lightAuto) lightOn = manualLight; if (!fanAuto) fanOn = manualFan; }
    return true;
  }
  return false;
}

void onCommand(char* topic, byte* payload, unsigned int length) {
  if (String(topic) != commandTopic) return;
  JsonDocument command;
  if (deserializeJson(command, payload, length)) return;
  if (!command["id"].is<const char*>() || !command["device"].is<const char*>()) return;
  String id = command["id"].as<String>();
  if (id.length() == 0 || id.length() > 64) return;
  if (id == lastCommandId) { publishState(); return; } // Do not count duplicate entry messages twice.
  lastCommandId = id;
  lastError = "";
  bool accepted = changeControl(command["device"].as<String>(), command["value"]);
  if (!accepted && lastError.length() == 0) lastError = "Invalid device command.";
  applyOutputs();
  publishState(); // Applied state (or explicit rejection), correlated with the command ID.
}

void readButtons() {
  for (int i = 0; i < 4; i++) {
    bool reading = digitalRead(BUTTON_PINS[i]);
    if (reading != rawButton[i]) { rawButton[i] = reading; changedAt[i] = millis(); }
    if (millis() - changedAt[i] >= 40 && stableButton[i] != reading) {
      stableButton[i] = reading;
      if (reading == LOW) {
        lastError = "";
        if (i == 0) occupancy(true);
        if (i == 1) occupancy(false);
        if (i == 2) daylight = !daylight;
        if (i == 3) {
          smoke = !smoke;
          if (!smoke) { if (!lightAuto) lightOn = manualLight; if (!fanAuto) fanOn = manualFan; }
        }
        applyOutputs();
        publishState();
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LIGHT_PIN, OUTPUT);
  pinMode(FAN_PIN, OUTPUT);
  pinMode(ALARM_PIN, OUTPUT);
  for (int pin : BUTTON_PINS) pinMode(pin, INPUT_PULLUP);
  sensor.setup(SENSOR_PIN, DHTesp::DHT22);
  stateTopic = String(ROOM_TOPIC) + "/state";
  commandTopic = String(ROOM_TOPIC) + "/command";
  availabilityTopic = String(ROOM_TOPIC) + "/availability";
  WiFi.begin("Wokwi-GUEST", "", 6);
  mqtt.setServer(BROKER, BROKER_PORT);
  mqtt.setCallback(onCommand);
  mqtt.setBufferSize(1024);
  mqtt.setKeepAlive(10);
  mqtt.setSocketTimeout(3);
  applyOutputs();
}

void loop() {
  unsigned long now = millis();
  if (WiFi.status() == WL_CONNECTED && !mqtt.connected() && (lastReconnect == 0 || now - lastReconnect >= 3000)) {
    lastReconnect = now;
    String clientId = "room-v2-" + String(esp_random(), HEX);
    if (mqtt.connect(clientId.c_str(), availabilityTopic.c_str(), 0, true, "offline")) {
      mqtt.subscribe(commandTopic.c_str());
      mqtt.publish(availabilityTopic.c_str(), "online", true);
      publishState();
    }
  }
  mqtt.loop();
  readButtons();
  if (now - lastReading >= 2000) {
    lastReading = now;
    TempAndHumidity reading = sensor.getTempAndHumidity();
    if (!isnan(reading.temperature)) temperature = reading.temperature;
  }
  applyOutputs();
  if (now - lastPublish >= 1000) { lastPublish = now; publishState(); }
  delay(10);
}
