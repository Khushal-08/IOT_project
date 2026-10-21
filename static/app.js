const $ = (id) => document.getElementById(id);
let room = null;
let busy = false;
let polling = false;
let lastMotion = null;
let lastEvent = null;
let movementTimer;
let mutationVersion = 0;

async function api(path, data) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 9000);
  try {
    const response = await fetch(path, {
      method: data === undefined ? 'GET' : 'POST',
      headers: data === undefined ? {} : {'Content-Type': 'application/json'},
      body: data === undefined ? undefined : JSON.stringify(data),
      signal: controller.signal,
    });
    const result = await response.json();
    if (result.state) render(result.state);
    if (!response.ok) throw new Error(result.message || 'Please try again.');
    return result;
  } catch (error) {
    if (error.name === 'AbortError' || error instanceof TypeError) {
      if (room) render({...room, online: false, temperature: null});
      throw new Error('Cannot reach the dashboard. Check that the server is running.');
    }
    throw error;
  } finally { clearTimeout(timer); }
}

function updateDisabled() {
  const unavailable = busy || !room?.online;
  ['light-toggle', 'fan-toggle', 'manual-mode', 'auto-mode', 'light-manual-mode', 'light-auto-mode'].forEach(id => $(id).disabled = unavailable || room?.smoke);
  $('temperature-input').disabled = unavailable;
  ['day-mode', 'night-mode', 'simulate-smoke', 'clear-smoke'].forEach(id => $(id).disabled = unavailable);
  $('enter-room').disabled = unavailable || room.people >= 8;
  $('exit-room').disabled = unavailable || room.people === 0;
  $('demo-connection').disabled = busy;
  ['play', 'reset', 'emergency'].forEach(action => $(`demo-${action}`).disabled = unavailable);
  $('demo-pause').disabled = busy || !room?.walkthrough?.running;
  $('send-button').disabled = busy || !$('chat-input').value.trim();
  document.querySelectorAll('[data-command]').forEach(button => button.disabled = busy);
}

function render(state) {
  room = state;
  $('walkthrough').hidden = state.source !== 'demo';
  const demo = state.walkthrough;
  if (demo) {
    $('demo-step').textContent = `${demo.label} · ${Math.floor(demo.elapsed)}s`;
    $('demo-progress').max = demo.duration;
    $('demo-progress').value = demo.elapsed;
    $('demo-play').textContent = demo.running ? 'Restart demo' : demo.step ? 'Play / resume' : 'Play demo';
    $('demo-pause').disabled = !demo.running || busy;
  }
  $('light-decision').textContent = state.decisions?.light || '';
  $('fan-decision').textContent = state.decisions?.fan || '';
  $('alarm-decision').textContent = state.decisions?.alarm || '';
  $('alarm-decision').classList.toggle('alarm-active', state.smoke);
  $('brightness-reading').textContent = state.online ? `${state.brightness_lux} lux · ${state.source === 'demo' ? 'simulated day/night sensor preset' : 'day/night preset'}` : 'Brightness unavailable';
  const online = state.online;
  $('connection').className = `connection ${online ? 'online' : 'offline'}`;
  $('connection-text').textContent = online ? 'Room connected' : 'Room disconnected';
  $('source-badge').textContent = state.source === 'demo' ? 'Local simulation' : 'Wokwi · MQTT';
  $('footer-source').textContent = state.source === 'demo' ? 'Local simulator' : 'ESP32 + MQTT';
  $('simulation').hidden = state.source !== 'demo';
  $('temperature').textContent = online && state.temperature !== null ? state.temperature.toFixed(1) : '—';
  $('condition').textContent = !online ? 'Sensor unavailable' : state.temperature > 30 ? 'Getting warm' : state.temperature < 22 ? 'A little cool' : 'Comfortable';
  $('condition').style.color = !online ? '#999' : state.temperature > 30 ? '#a78260' : '#63856f';
  $('sensor-note').textContent = online ? (state.source === 'demo' ? 'Simulated temperature input' : 'Live room reading') : 'Waiting for connection';
  $('room-scene').classList.toggle('is-lit', online && state.light);
  $('room-scene').classList.toggle('is-fan-on', online && state.fan);
  $('room-scene').classList.toggle('is-offline', !online);
  $('room-scene').classList.toggle('is-night', !state.daylight);
  $('room-scene').classList.toggle('has-smoke', online && state.smoke);
  $('safety-banner').hidden = !online || !state.smoke;
  $('occupancy-badge').textContent = `${state.people} inside`;
  $('room-context').textContent = `${state.daylight ? 'Daytime' : 'Nighttime'} · ${state.people ? `${state.people} ${state.people === 1 ? 'person' : 'people'} inside` : 'room empty'}`;
  $('day-mode').setAttribute('aria-pressed', String(state.daylight));
  $('night-mode').setAttribute('aria-pressed', String(!state.daylight));
  $('simulate-smoke').textContent = state.smoke ? 'Clear smoke' : 'Simulate smoke';
  $('countdown-banner').hidden = !online || state.smoke || state.countdown === null;
  $('countdown-value').textContent = state.countdown ?? 0;
  const people = Array.from($('room-people').children);
  people.forEach((person, index) => person.style.display = index < state.people ? '' : 'none');
  if (lastMotion !== null && state.motion.id !== lastMotion && online) animatePerson(state.motion.direction);
  lastMotion = state.motion.id;
  $('room-offline-message').hidden = online;
  $('scene-light-label').textContent = online ? (state.light ? 'Light on' : 'Light off') : 'Light unavailable';
  $('scene-fan-label').textContent = online ? (state.fan ? 'Fan running' : 'Fan stopped') : 'Fan unavailable';
  $('room-illustration').setAttribute('aria-label', online
    ? `Living room. ${state.people} ${state.people === 1 ? 'person' : 'people'} inside. ${state.daylight ? 'Day' : 'Night'}. Light ${state.light ? 'on' : 'off'}. Fan ${state.fan ? 'running' : 'stopped'}. ${state.smoke ? 'Smoke alert.' : ''} Temperature ${state.temperature} degrees Celsius.`
    : 'Living room unavailable. Reconnect to see live device changes.');
  for (const device of ['light', 'fan']) {
    $(`${device}-card`).classList.toggle('on', online && state[device]);
    $(`${device}-status`).textContent = online ? (state[device] ? 'On' : 'Off') : 'Offline';
    $(`${device}-toggle`).setAttribute('aria-checked', String(state[device]));
  }
  $('light-caption').textContent = !online ? 'Device unavailable' : state.light ? 'Light is on' : 'Light is off';
  $('manual-mode').setAttribute('aria-pressed', String(state.fan_mode === 'manual'));
  $('auto-mode').setAttribute('aria-pressed', String(state.fan_mode === 'auto'));
  $('light-manual-mode').setAttribute('aria-pressed', String(state.light_mode === 'manual'));
  $('light-auto-mode').setAttribute('aria-pressed', String(state.light_mode === 'auto'));
  $('fan-description').textContent = state.fan_mode === 'auto' ? 'Adjusts with room temperature.' : 'Keep the air moving.';
  $('demo-connection').textContent = online ? 'Disconnect simulator' : 'Reconnect simulator';
  if (online && document.activeElement !== $('temperature-input')) {
    $('temperature-input').value = state.temperature;
    $('temperature-output').textContent = `${state.temperature.toFixed(1)}°C`;
  }
  const energy = state.energy;
  $('energy-wh').textContent = (energy.total_kwh * 1000).toFixed(3);
  $('energy-cost').textContent = `₹${energy.cost.toFixed(4)}`;
  $('energy-saved').textContent = energy.saved_wh.toFixed(3);
  $('light-runtime').textContent = duration(energy.light_seconds);
  $('fan-runtime').textContent = duration(energy.fan_seconds);
  const totalWh = energy.light_wh + energy.fan_wh;
  $('light-energy-bar').style.width = `${totalWh ? energy.light_wh / totalWh * 100 : 0}%`;
  $('fan-energy-bar').style.width = `${totalWh ? energy.fan_wh / totalWh * 100 : 0}%`;
  $('event-count').textContent = `${state.events.length} ${state.events.length === 1 ? 'event' : 'events'}`;
  if (state.events[0]?.id !== lastEvent) {
    lastEvent = state.events[0]?.id;
    $('activity-log').replaceChildren(...state.events.slice(0, 25).map(event => {
      const item = document.createElement('li');
      item.className = event.level;
      const time = document.createElement('time');
      time.dateTime = event.time;
      time.textContent = new Date(event.time).toLocaleTimeString([], {hour12: false});
      const text = document.createElement('span');
      text.textContent = event.text;
      item.append(time, text);
      return item;
    }));
  }
  updateDisabled();
}

function duration(seconds) {
  return seconds < 60 ? `${Math.floor(seconds)}s` : `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

function animatePerson(direction) {
  clearTimeout(movementTimer);
  const actor = $('walking-person');
  actor.classList.remove('person-enter', 'person-exit');
  // Restart a new movement event even when consecutive people enter together.
  void actor.getBoundingClientRect();
  actor.classList.add(direction === 'enter' ? 'person-enter' : 'person-exit');
  $('room-door-leaf').classList.add('door-open');
  movementTimer = setTimeout(() => {
    actor.classList.remove('person-enter', 'person-exit');
    $('room-door-leaf').classList.remove('door-open');
  }, 1700);
}

function notice(message = '') {
  $('notice').textContent = message;
  $('notice').hidden = !message;
}

async function perform(task, progress = 'Sending command…') {
  if (busy) return;
  mutationVersion += 1;
  busy = true;
  updateDisabled();
  notice();
  $('chat-footnote').textContent = progress;
  try { await task(); }
  catch (error) { notice(error.message); }
  finally {
    busy = false;
    updateDisabled();
    $('chat-footnote').textContent = 'Simple commands for your room.';
  }
}

function addMessage(text, kind = 'assistant', error = false) {
  const element = document.createElement('div');
  element.className = `message ${kind}${error ? ' error' : ''}`;
  const label = document.createElement('span');
  label.className = 'message-label';
  label.textContent = kind === 'user' ? 'YOU' : 'HOME';
  const paragraph = document.createElement('p');
  paragraph.textContent = text;
  element.append(label, paragraph);
  $('messages').append(element);
  $('messages').scrollTop = $('messages').scrollHeight;
}

async function sendCommand(text) {
  text = text.trim();
  if (!text || busy) return;
  $('chat-input').value = '';
  addMessage(text, 'user');
  await perform(async () => {
    try {
      const result = await api('/api/chat', {message: text});
      addMessage(result.message);
    } catch (error) {
      addMessage(error.message, 'assistant', true);
      throw error;
    }
  });
  $('chat-input').focus();
}

for (const device of ['light', 'fan']) {
  $(`${device}-toggle`).addEventListener('click', () => {
    const value = !room[device];
    perform(() => api('/api/control', {device, value}), `Turning ${device} ${value ? 'on' : 'off'}…`);
  });
}
for (const mode of ['manual', 'auto']) {
  $(`${mode}-mode`).addEventListener('click', () => perform(() => api('/api/control', {device: 'fan_mode', value: mode})));
  $(`light-${mode}-mode`).addEventListener('click', () => perform(() => api('/api/control', {device: 'light_mode', value: mode})));
}
const control = (device, value) => perform(() => api('/api/control', {device, value}));
$('enter-room').addEventListener('click', () => control('entry', 'enter'));
$('exit-room').addEventListener('click', () => control('entry', 'exit'));
$('day-mode').addEventListener('click', () => control('daylight', true));
$('night-mode').addEventListener('click', () => control('daylight', false));
$('simulate-smoke').addEventListener('click', () => control('smoke', !room.smoke));
$('clear-smoke').addEventListener('click', () => control('smoke', false));
$('chat-form').addEventListener('submit', event => {
  event.preventDefault();
  sendCommand($('chat-input').value);
});
$('chat-input').addEventListener('input', updateDisabled);
document.querySelectorAll('[data-command]').forEach(button => button.addEventListener('click', () => sendCommand(button.dataset.command)));
$('temperature-input').addEventListener('input', event => $('temperature-output').textContent = `${Number(event.target.value).toFixed(1)}°C`);
$('temperature-input').addEventListener('change', event => perform(() => api('/api/demo', {temperature: Number(event.target.value)}), 'Updating room temperature…'));
$('demo-connection').addEventListener('click', () => perform(() => api('/api/demo', {online: !room.online}), 'Updating connection…'));

async function poll() {
  if (busy || polling) return;
  polling = true;
  const versionAtStart = mutationVersion;
  try {
    const state = await api('/api/state');
    if (!busy && versionAtStart === mutationVersion) render(state);
  } catch (error) {
    if (!busy) {
      $('connection-text').textContent = 'Server unavailable';
      $('connection').className = 'connection offline';
      notice(error.message);
    }
  } finally { polling = false; }
}
for (const action of ['play', 'pause', 'reset', 'emergency']) {
  $(`demo-${action}`).addEventListener('click', () => perform(() => api('/api/walkthrough', {action})));
}
let soundEnabled = false;
let audioContext;
$('alarm-sound').addEventListener('click', () => {
  soundEnabled = !soundEnabled;
  if (soundEnabled) {
    audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
    audioContext.resume();
  }
  $('alarm-sound').textContent = soundEnabled ? 'Sound on' : 'Sound off';
  $('alarm-sound').setAttribute('aria-pressed', String(soundEnabled));
});
setInterval(() => {
  if (!soundEnabled || !room?.online || !room.smoke || !audioContext) return;
  const tone = audioContext.createOscillator();
  const gain = audioContext.createGain();
  gain.gain.value = 0.05;
  tone.frequency.value = 740;
  tone.connect(gain); gain.connect(audioContext.destination);
  tone.start(); tone.stop(audioContext.currentTime + 0.18);
}, 900);
updateDisabled();
poll();
setInterval(poll, 700);
