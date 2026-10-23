/* Bosch Local Dishwasher card. No framework or third-party cards required. */
class BoschLocalCard extends HTMLElement {
  setConfig(config) {
    for (const key of ["program", "armed", "start", "clear", "automatic", "last_run", "status"]) {
      if (typeof config[key] !== "string" || !config[key].includes(".")) {
        throw new Error(`bosch-local-card requires an entity ID for '${key}'`);
      }
    }
    this._config = { name: "Dishwasher", ...config };
    this._options = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding:20px; }
        h2 { display:flex; align-items:center; gap:10px; font-size:20px; margin:0 0 18px; }
        .row { display:flex; gap:12px; align-items:center; margin:12px 0; }
        label { flex:1; } select { flex:1; min-width:0; }
        select,button { font:inherit; color:var(--primary-text-color); background:var(--secondary-background-color); border:1px solid var(--divider-color); border-radius:12px; padding:12px; }
        button { cursor:pointer; } button:disabled,select:disabled { opacity:.5; cursor:default; }
        button[aria-pressed="true"] { color:var(--success-color,#228b45); border-color:currentColor; }
        #time { width:100%; text-align:left; }
        .muted { color:var(--secondary-text-color); font-size:14px; }
        #error { color:var(--error-color); margin-top:12px; }
        #clear { width:100%; margin-top:12px; }
        ha-icon { --mdc-icon-size:24px; }
      </style>
      <ha-card>
        <h2><ha-icon icon="mdi:dishwasher"></ha-icon><span id="title"></span></h2>
        <div class="row"><select id="program" aria-label="Scheduled program"></select>
          <button id="armed" aria-pressed="false">Schedule</button></div>
        <button id="time"><ha-icon icon="mdi:clock-start"></ha-icon> <span></span></button>
        <div class="row"><label for="automatic">Automatic NightWash<br><span class="muted">Next 01:00 after 48 hours</span></label>
          <button id="automatic" aria-pressed="false">Off</button></div>
        <div id="status" class="muted" role="status"></div>
        <div id="reason" class="muted"></div>
        <div id="last" class="muted"></div>
        <button id="clear"><ha-icon icon="mdi:calendar-remove"></ha-icon> Clear schedule</button>
        <div id="error" role="alert" hidden></div>
      </ha-card>`;
    this.shadowRoot.getElementById("title").textContent = this._config.name;
    this.shadowRoot.getElementById("program").onchange = (event) =>
      this._call("select", "select_option", this._config.program, { option: event.target.value });
    for (const key of ["armed", "automatic"]) {
      this.shadowRoot.getElementById(key).onclick = () => this._call(
        "switch", this._hass.states[this._config[key]]?.state === "on" ? "turn_off" : "turn_on", this._config[key]);
    }
    this.shadowRoot.getElementById("time").onclick = () => this.dispatchEvent(new CustomEvent(
      "hass-more-info", { detail: { entityId: this._config.start }, bubbles: true, composed: true }));
    this.shadowRoot.getElementById("clear").onclick = () =>
      this._call("button", "press", this._config.clear);
    if (this._hass) this.hass = this._hass;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config || !this.shadowRoot) return;
    const get = (key) => hass.states[this._config[key]];
    const usable = (key) => get(key) && !["unknown", "unavailable"].includes(get(key).state);
    const select = this.shadowRoot.getElementById("program");
    const options = get("program")?.attributes.options || [];
    if (JSON.stringify(options) !== this._options) {
      select.replaceChildren(...options.map((name) => {
        const option = document.createElement("option");
        option.value = name; option.textContent = name;
        return option;
      }));
      this._options = JSON.stringify(options);
    }
    select.value = get("program")?.state || "";
    select.disabled = !usable("program") || !!this._busy;
    for (const key of ["armed", "automatic"]) {
      const button = this.shadowRoot.getElementById(key);
      const on = get(key)?.state === "on";
      button.setAttribute("aria-pressed", String(on));
      button.textContent = key === "armed" ? (on ? "Scheduled" : "Schedule") : (on ? "On" : "Off");
      button.disabled = !usable(key) || !!this._busy;
    }
    this.shadowRoot.getElementById("time").disabled = !get("start");
    this.shadowRoot.querySelector("#time span").textContent =
      usable("start") ? `Start: ${this._date(get("start").state)}` : "Set start date and time";
    this.shadowRoot.getElementById("clear").disabled = !get("clear") || get("clear").state === "unavailable" || !!this._busy;
    this.shadowRoot.getElementById("status").textContent = get("status")?.state || "Schedule status unavailable";
    const statusAttributes = get("status")?.attributes || {};
    const reasons = statusAttributes.automatic_reasons;
    this.shadowRoot.getElementById("reason").textContent =
      Array.isArray(reasons) && reasons.length ? reasons.join(". ") : (statusAttributes.automatic_summary || "");
    this.shadowRoot.getElementById("last").textContent =
      `Last completed wash: ${usable("last_run") ? this._date(get("last_run").state) : "Unknown"}`;
    const missing = Object.keys(this._config).filter((key) =>
      ["program", "armed", "start", "clear", "automatic", "last_run", "status"].includes(key) && !get(key));
    const message = this._callError || (missing.length ? `Missing entities: ${missing.join(", ")}` : get("status")?.attributes.error);
    const error = this.shadowRoot.getElementById("error");
    error.textContent = message || "";
    error.hidden = !message;
  }

  _date(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString(this._hass.locale?.language, { timeZone: this._hass.config?.time_zone });
  }

  async _call(domain, service, entity, data = {}) {
    if (this._busy) return;
    this._busy = true; this._callError = null; this.hass = this._hass;
    try {
      await this._hass.callService(domain, service, { entity_id: entity, ...data });
    } catch (error) {
      this._callError = error.message || String(error);
    } finally {
      this._busy = false; this.hass = this._hass;
    }
  }

  getCardSize() { return 5; }
}

if (!customElements.get("bosch-local-card")) customElements.define("bosch-local-card", BoschLocalCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "bosch-local-card", name: "Bosch Local Dishwasher", description: "Local NightWash scheduling and completed-wash history" });
