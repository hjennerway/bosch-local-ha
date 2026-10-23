const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// DOM boundary double for the card's HA service contract.
function card() {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      textContent: '', hidden: false,
      setAttribute(key, value) { this[key] = value; },
      replaceChildren(...children) { this.children = children; },
    });
    return elements.get(id);
  };
  let Card;
  const context = {
    HTMLElement: class {
      attachShadow() { this.shadowRoot = { getElementById: element, querySelector: element }; }
      dispatchEvent(event) { this.event = event; }
    },
    CustomEvent: class { constructor(type, init) { this.type = type; Object.assign(this, init); } },
    customElements: { get() {}, define(_name, cls) { Card = cls; } },
    window: {}, document: { createElement: () => ({}) },
  };
  vm.runInNewContext(fs.readFileSync('custom_components/bosch_local/frontend/bosch-local-card.js', 'utf8'), context);
  const instance = new Card();
  const config = Object.fromEntries(['program', 'armed', 'start', 'clear', 'automatic', 'last_run', 'status']
    .map(key => [key, `test.${key}`]));
  instance.setConfig(config);
  const calls = [];
  instance.hass = {
    states: Object.fromEntries(Object.values(config).map(id => [id, { state: 'off', attributes: {} }])),
    callService: async (...args) => calls.push(args), config: { time_zone: 'Europe/London' },
  };
  return { instance, element, calls };
}

test('clear uses only the local button, never MQTT', async () => {
  const { element, calls } = card();
  await element('clear').onclick();
  assert.deepEqual(calls[0].slice(0, 2), ['button', 'press']);
  assert.equal(calls[0][2].entity_id, 'test.clear');
});

test('schedule and automatic toggles route independently', async () => {
  const { element, calls } = card();
  await element('armed').onclick();
  await element('automatic').onclick();
  assert.equal(calls[0][2].entity_id, 'test.armed');
  assert.equal(calls[1][2].entity_id, 'test.automatic');
});

test('start date opens the HA date editor', () => {
  const { instance, element } = card();
  element('time').onclick();
  assert.equal(instance.event.type, 'hass-more-info');
  assert.equal(instance.event.detail.entityId, 'test.start');
});

test('service errors are displayed and controls recover', async () => {
  const { instance, element } = card();
  instance._hass.callService = async () => { throw new Error('Set a future start time first'); };
  await element('armed').onclick();
  assert.equal(element('error').textContent, 'Set a future start time first');
  assert.equal(element('armed').disabled, false);
});

test('missing entities are shown and unavailable controls disabled', () => {
  const { instance, element } = card();
  delete instance._hass.states['test.program'];
  instance._hass.states['test.armed'].state = 'unavailable';
  instance.hass = instance._hass;
  assert.equal(element('program').disabled, true);
  assert.equal(element('armed').disabled, true);
  assert.match(element('error').textContent, /Missing entities: program/);
});
