/* PGE 0.5.0: independent Lovelace modules, no external libraries. */
import "./pge-settings.js?v=0.5.0";
const VERSION = "0.5.0";
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const fmt = (v) =>
  v == null || !Number.isFinite(Number(v))
    ? "—"
    : new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 0 }).format(
        Math.abs(Number(v)) < 0.5 ? 0 : Number(v),
      );
const day = (v) => (v ? v.split("-").reverse().join(".") : "—");
const month = (v) =>
  v
    ? new Intl.DateTimeFormat("pl-PL", {
        month: "long",
        year: "numeric",
        timeZone: "UTC",
      }).format(new Date(`${v}-01T12:00:00Z`))
    : "—";
const shortMonth = (v) =>
  v
    ? new Intl.DateTimeFormat("pl-PL", {
        month: "short",
        timeZone: "UTC",
      }).format(new Date(`${v}-01T12:00:00Z`))
    : "—";
const coreMetrics = {
  available_energy: ["Magazyn PGE", "mdi:transmission-tower", "#7b61c4"],
  deficit: ["Niedobór", "mdi:alert-circle-outline", "#bd6639"],
  period_balance: ["Zmiana od faktury", "mdi:swap-vertical", "#278680"],
  carried_balance: [
    "Po ostatniej fakturze",
    "mdi:file-document-outline",
    "#607d8b",
  ],
  import_since_settlement: ["Pobrano od faktury", "mdi:arrow-down", "#3287bd"],
  credited_since_settlement: ["Oddano od faktury", "mdi:arrow-up", "#ab63b4"],
};
const css = `:host{display:block;-webkit-user-select:text;user-select:text;--pge-blue:#3287bd;--pge-teal:#278680;--pge-purple:#7b61c4;--pge-orange:#e6a020}*{box-sizing:border-box}ha-card{padding:20px;border-radius:20px;overflow:hidden;color:var(--primary-text-color,#24333c)}h2{font-size:17px;margin:0;font-weight:650}h3{font-size:14px;margin:0}.head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:16px}.sub{font-size:12px;color:var(--secondary-text-color,#6a7c87);line-height:1.5}.chip{font-size:11px;padding:5px 9px;border-radius:20px;background:var(--secondary-background-color,#f1f5f6);white-space:nowrap}.row{display:flex;gap:12px;align-items:center}.seg{display:flex;background:var(--secondary-background-color,#f1f5f6);border-radius:20px;padding:3px}.seg button{border-radius:16px;padding:6px 12px;font-size:12px}.seg .active{background:var(--card-background-color,#fff);box-shadow:0 1px 4px #0002}button{font:inherit;color:inherit;background:transparent;border:0;cursor:pointer;padding:8px;border-radius:8px}button:hover{background:var(--secondary-background-color,#f0f4f5)}button:focus-visible,summary:focus-visible{outline:2px solid var(--primary-color,#3287bd);outline-offset:2px}.primary{background:var(--primary-color,#3287bd);color:white;padding:10px 16px}.primary:hover{filter:brightness(.94);background:var(--primary-color,#3287bd)}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}th,td{text-align:right;border-bottom:1px solid var(--divider-color,#e7edef);padding:10px 6px;white-space:nowrap}th{font-size:10px;color:var(--secondary-text-color,#667b85);font-weight:500}th:first-child,td:first-child{text-align:left}td small{display:block;font-size:10px;color:var(--secondary-text-color)}td.balance{font-weight:700}td.plus{color:var(--pge-teal)}td.minus{color:var(--pge-blue)}.month-row{cursor:pointer}.month-row:hover{background:var(--secondary-background-color,#f5f8f8)}.month-row button{padding:0;font-weight:600}.details-cell{padding:0 0 14px;background:var(--secondary-background-color,#f5f8f8)}.details-cell table{font-size:11px}.daily-table{max-height:330px;overflow:auto}.daily-table thead{position:sticky;top:0;background:var(--card-background-color,#fff);z-index:1}.details-cell td,.details-cell th{padding:7px 6px}.small-chart{padding:12px 4px 0}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--secondary-text-color);margin:12px 0}.legend span{display:flex;align-items:center;gap:5px}.dot{height:7px;width:15px;border-radius:5px;background:var(--c)}svg.chart{width:100%;height:auto;max-height:240px;display:block;overflow:visible}svg.chart text{fill:var(--secondary-text-color,#647985);font-size:10px}svg.chart .grid{stroke:var(--divider-color,#e0e8eb);stroke-dasharray:3 4}.empty{font-size:12px;color:var(--secondary-text-color);padding:12px 0}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0 16px}.stat{background:var(--secondary-background-color,#f4f7f8);border-radius:12px;padding:12px 10px}.stat strong{display:block;font-size:21px;margin:4px 0}.stat small{font-size:10px;color:var(--secondary-text-color)}details>summary{cursor:pointer;font-size:12px;color:var(--secondary-text-color);padding:10px 0}ha-icon{--mdc-icon-size:22px}select,input{font:inherit;background:var(--card-background-color,#fff);color:var(--primary-text-color);border:1px solid var(--divider-color,#dbe3e7);padding:10px;border-radius:9px;max-width:100%}.warn{color:#b45a2d;font-size:12px}.error{color:var(--error-color,#b3261e)}@media(max-width:450px){ha-card{padding:16px 12px}th,td{padding:9px 4px}.stat{padding:9px 7px}.stat strong{font-size:18px}.head{gap:6px}.legend{gap:9px;font-size:10px}}`;
// A single HA subscription per connection and entry, shared by all independent modules.
const hubs = new WeakMap();
function connect(hass, entry, listener) {
  let entries = hubs.get(hass.connection);
  if (!entries) hubs.set(hass.connection, (entries = new Map()));
  const key = entry || "auto";
  let hub = entries.get(key);
  if (!hub) {
    hub = { listeners: new Set() };
    entries.set(key, hub);
    hub.ready = hass.connection.subscribeMessage(
      (data) => {
        hub.data = data;
        for (const fn of hub.listeners) fn(data);
      },
      { type: "pge_storage/subscribe", ...(entry ? { entry_id: entry } : {}) },
    );
    hub.ready.catch((error) => {
      for (const fn of hub.listeners)
        fn({ error: error.message || String(error) });
    });
  }
  hub.listeners.add(listener);
  if (hub.data) listener(hub.data);
  return () => {
    hub.listeners.delete(listener);
    if (!hub.listeners.size) {
      entries.delete(key);
      hub.ready.then((stop) => stop()).catch(() => {});
    }
  };
}
function chart(labels, series, { height = 210 } = {}) {
  if (!series.some((s) => s.values.some((v) => v != null)))
    return '<div class="empty" style="text-align:center;padding:32px 8px">Brak odczytów do wykresu</div>';
  const width = 660,
    left = 44,
    right = 48,
    top = 25,
    bottom = 32,
    w = width - left - right,
    h = height - top - bottom;
  const bounds = (axis) => {
    const values = series
      .filter((s) => (s.axis || 0) === axis)
      .flatMap((s) => s.values.filter((v) => v != null).map(Number));
    const min = Math.min(0, ...values),
      max = Math.max(1, ...values);
    return { min, max: max === min ? min + 1 : max };
  };
  const axes = [bounds(0), bounds(1)],
    x = (i) =>
      left + (labels.length < 2 ? w / 2 : (i * w) / (labels.length - 1)),
    y = (v, a = 0) =>
      top + h - ((Number(v) - axes[a].min) * h) / (axes[a].max - axes[a].min);
  let result = `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(series.map((s) => s.name).join(", "))}"><text x="${left}" y="12">Pobór / oddanie · kWh</text><text x="${width - right}" y="12" text-anchor="end">Magazyn · kWh</text>`;
  for (let i = 0; i < 4; i++) {
    const f = i / 3,
      yy = top + h - f * h;
    result += `<line class="grid" x1="${left}" x2="${width - right}" y1="${yy}" y2="${yy}"/><text x="${left - 7}" y="${yy + 3}" text-anchor="end">${fmt(axes[0].min + f * (axes[0].max - axes[0].min))}</text><text x="${width - right + 7}" y="${yy + 3}">${fmt(axes[1].min + f * (axes[1].max - axes[1].min))}</text>`;
  }
  series.forEach((s) => {
    let segment = [];
    const flush = () => {
      if (segment.length > 1)
        result += `<polyline points="${segment.join(" ")}" fill="none" stroke="${s.color}" stroke-width="${s.axis ? 3 : 2}" ${s.dash ? 'stroke-dasharray="5 4"' : ""}/>`;
      segment = [];
    };
    s.values.forEach((value, i) => {
      if (value == null) {
        flush();
        return;
      }
      const xx = x(i),
        yy = y(value, s.axis || 0);
      segment.push(`${xx},${yy}`);
      result += `<circle cx="${xx}" cy="${yy}" r="3.5" fill="${s.color}"><title>${esc(labels[i])} · ${esc(s.name)}: ${fmt(value)} kWh</title></circle>`;
    });
    flush();
  });
  labels.forEach((label, i) => {
    if (
      labels.length < 13 ||
      i % Math.ceil(labels.length / 9) === 0 ||
      i === labels.length - 1
    )
      result += `<text x="${x(i)}" y="${height - 10}" text-anchor="middle">${esc(label)}</text>`;
  });
  return result + "</svg>";
}
const legend = (items) =>
  `<div class="legend">${items.map(([title, color]) => `<span><i class="dot" style="--c:${color}"></i>${esc(title)}</span>`).join("")}</div>`;

class PGEBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.config = {};
  }
  setConfig(config) {
    this.config = { ...config };
    this.stop?.();
    this.stop = null;
    this._connect();
    if (this.data) this.render();
  }
  set hass(hass) {
    this._hass = hass;
    this._connect();
    this.onHass?.();
  }
  connectedCallback() {
    this._connect();
  }
  disconnectedCallback() {
    this.stop?.();
    this.stop = null;
    this.onClose?.();
  }
  _connect() {
    if (!this.isConnected || !this._hass || this.stop) return;
    this.stop = connect(this._hass, this.config.entry_id, (data) => {
      this.data = data;
      if (data.error) {
        this.frame("");
        return;
      }
      if (data.loaded === false) {
        this.frame(
          '<ha-card><div class="empty">Integracja jest wyłączona lub przeładowywana.</div></ha-card>',
        );
        return;
      }
      this.render();
    });
  }
  getCardSize() {
    return 5;
  }
  getGridOptions() {
    return { columns: 12, rows: "auto" };
  }
  static getConfigElement() {
    return window.document.createElement("pge-card-editor");
  }
  async call(action, values = {}) {
    if (!this.data?.entry_id)
      throw new Error("Poczekaj na wczytanie integracji.");
    return this._hass.callWS({
      type: `pge_storage/${action}`,
      entry_id: this.data.entry_id,
      ...values,
    });
  }
  frame(content) {
    this.shadowRoot.innerHTML = `<style>${css}</style>${this.data?.error ? `<ha-card><div class="error">${esc(this.data.error)}</div></ha-card>` : content}`;
  }
  info(key) {
    const entity =
      this.data?.entities?.[key] || this.data?.energy?.config?.sources?.[key];
    if (entity)
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          detail: { entityId: entity },
          bubbles: true,
          composed: true,
        }),
      );
  }
}
class BalanceCard extends PGEBase {
  getGridOptions() {
    return { columns: 4, rows: 2 };
  }
  static getStubConfig() {
    return { metric: "available_energy" };
  }
  getCardSize() {
    return 2;
  }
  render() {
    const key = this.config.metric || "available_energy",
      [title, icon, color] = coreMetrics[key] || coreMetrics.available_energy;
    const current = this.data.current || {},
      inventory = this.data.planning?.inventory;
    let value = current[key] ?? current[`${key}_kwh`];
    if (inventory && key === "available_energy")
      value = Math.max(0, Number(inventory.balance_kwh));
    if (inventory && key === "deficit")
      value = Math.max(0, -Number(inventory.balance_kwh));
    this.frame(
      `<ha-card style="padding:16px"><button id="metric" style="width:100%;text-align:left;padding:0"><div class="row"><ha-icon icon="${icon}" style="color:${color};background:${color}15;border-radius:12px;padding:10px;box-sizing:content-box"></ha-icon><span class="sub">${esc(this.config.title || title)}</span></div><div style="font-size:32px;font-weight:700;margin-top:14px">${fmt(value)} <small style="font-size:14px;font-weight:400">kWh</small></div></button></ha-card>`,
    );
    this.shadowRoot
      .getElementById("metric")
      ?.addEventListener("click", () => this.info(key));
  }
}
class EnergyCard extends PGEBase {
  constructor() {
    super();
    this.mode = "today";
  }
  render() {
    const data = this.data.energy || { values: {}, today: {}, consumers: [] },
      v = data.values,
      t = data.today,
      power = this.mode === "power",
      unit = power ? "W" : "kWh";
    const available =
      this.data.planning?.inventory?.balance_kwh ??
      this.data.current?.available_energy;
    const nodes = [
      {
        key: "pv",
        name: "Słońce",
        icon: "mdi:solar-power",
        x: 50,
        y: 15,
        color: "#e6a020",
        value: power ? v.pv_power : t.pv_energy,
        entity: power ? "pv_power" : "pv_today",
      },
      {
        key: "grid",
        name: "Sieć",
        icon: "mdi:transmission-tower",
        x: 16,
        y: 52,
        color: "#3287bd",
        value: power ? v.grid_import_power : t.grid_import_energy,
        other: power ? v.grid_export_power : t.grid_export_energy,
        entity: power ? "grid_import_power" : "grid_import_today",
      },
      {
        key: "home",
        name: "Dom",
        icon: "mdi:home",
        x: 50,
        y: 52,
        color: "#278680",
        value: power ? v.home_power : t.home_energy,
        entity: power ? "home_power" : "home_today",
      },
      {
        key: "pge",
        name: "Magazyn PGE",
        icon: "mdi:cloud-outline",
        x: 84,
        y: 52,
        color: "#7b61c4",
        value: available == null ? null : Math.max(0, Number(available)),
        entity: "available_energy",
        unit: "kWh",
      },
      {
        key: "battery",
        name: "Akumulator",
        icon: "mdi:battery",
        x: 50,
        y: 89,
        color: "#32aaa4",
        value: v.battery_soc ?? v.battery_stored,
        unit: v.battery_soc != null ? "%" : "kWh",
        other: power ? v.battery_discharge_power : t.battery_discharge_energy,
        charge: power ? v.battery_charge_power : t.battery_charge_energy,
        entity: "battery_soc",
      },
    ];
    this.frame(
      `<style>.flow{position:relative;aspect-ratio:400/360;max-width:500px;margin:0 auto 12px}.flow svg{position:absolute;width:100%;height:100%;overflow:visible}.node{position:absolute;transform:translate(-50%,-50%);width:98px;text-align:center;padding:0;background:none!important}.orb{width:82px;height:82px;margin:0 auto;border:2px solid var(--c);border-radius:50%;background:var(--card-background-color,#fff);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px}.orb ha-icon{--mdc-icon-size:23px}.orb strong{font-size:14px;font-weight:550}.node small{display:block;font-size:10px;margin-top:5px;color:var(--secondary-text-color)}.node .secondary{font-size:10px;color:var(--c)}.node-home .orb{border-width:3px}.consumers{display:grid;gap:11px;margin-top:12px}.consumer .bar{height:4px;background:var(--secondary-background-color,#edf2f3);border-radius:5px;margin-top:5px}.consumer .bar i{height:100%;display:block;background:var(--pge-teal);border-radius:5px}@media(max-width:380px){.orb{width:72px;height:72px}.orb strong{font-size:12px}.node{width:85px}}</style><ha-card><div class="head"><h2>${esc(this.config.title || "Energia w domu")}</h2><div class="seg"><button data-mode="power" class="${power ? "active" : ""}">Teraz</button><button data-mode="today" class="${!power ? "active" : ""}">Dzisiaj</button></div></div><div class="flow"><svg viewBox="0 0 400 360" aria-hidden="true"><path d="M200 95V143" stroke="#e6a020" stroke-width="2" fill="none"/><path d="M105 187H158" stroke="#3287bd" stroke-width="2" fill="none"/><path d="M242 187H295" stroke="#7b61c4" stroke-width="2" stroke-dasharray="4 5" fill="none"/><path d="M200 230V278" stroke="#32aaa4" stroke-width="2" fill="none"/></svg>${nodes.map((n) => `<button class="node node-${n.key}" data-entity="${n.entity}" style="left:${n.x}%;top:${n.y}%;--c:${n.color}" title="${esc(n.name)}"><div class="orb"><ha-icon icon="${n.icon}"></ha-icon><strong>${n.key === "grid" ? "↓ " : ""}${fmt(n.value)} ${n.unit || unit}</strong>${n.key === "grid" ? `<span class="secondary">↑ ${fmt(n.other)} ${unit}</span>` : ""}</div><small>${n.name}</small>${n.key === "battery" ? `<span class="secondary">↓ ${fmt(n.charge)} · ↑ ${fmt(n.other)} ${unit}</span>` : ""}</button>`).join("")}</div><div class="sub" style="text-align:center">${power ? "Bieżąca moc" : "Przepływy dzisiaj"} · PGE: energia do odbioru po opuście</div>${
        data.consumers.length
          ? `<div class="consumers">${data.consumers
              .map((c, i) => {
                const value = power ? c.power_w : c.today_kwh,
                  total = power ? v.home_power : t.home_energy;
                return `<div class="consumer"><button data-consumer="${i}" style="padding:0;width:100%;display:flex;justify-content:space-between;font-size:12px"><span>${esc(c.name)}</span><strong>${fmt(value)} ${unit}</strong></button><div class="bar"><i style="width:${value != null && total > 0 ? Math.min(100, (100 * Number(value)) / Number(total)) : 0}%"></i></div></div>`;
              })
              .join("")}</div>`
          : ""
      }${!Object.keys(data.config?.sources || {}).length ? '<div class="sub" style="text-align:center;margin-top:12px">Wybierz PV, dom i akumulator w konfiguratorze źródeł.</div>' : ""}</ha-card>`,
    );
    for (const b of this.shadowRoot.querySelectorAll("[data-mode]"))
      b.onclick = () => {
        this.mode = b.dataset.mode;
        this.render();
      };
    for (const b of this.shadowRoot.querySelectorAll("[data-entity]"))
      b.onclick = () => this.info(b.dataset.entity);
    for (const b of this.shadowRoot.querySelectorAll("[data-consumer]"))
      b.onclick = () => {
        const c = data.consumers[Number(b.dataset.consumer)],
          entity = power ? c.power : c.energy;
        if (entity)
          this.dispatchEvent(
            new CustomEvent("hass-more-info", {
              detail: { entityId: entity },
              bubbles: true,
              composed: true,
            }),
          );
      };
  }
}
class HistoryCard extends PGEBase {
  constructor() {
    super();
    this.days = new Map();
    this.expanded = new Set();
  }
  render() {
    if (!this.shadowRoot.querySelector("ha-card")) {
      this.frame(
        `<ha-card><div class="head"><h2>${esc(this.config.title || "Rozliczenie miesięczne")}</h2><button id="refresh" title="Odśwież">↻</button></div><div id="monthly-chart"></div><div class="scroll"><table><thead><tr><th>Miesiąc</th><th>Pobrano</th><th>Oddano</th><th>Magazyn</th><th>Netto</th></tr></thead><tbody id="months"></tbody></table></div><div id="history-note" class="sub">Wczytywanie miesięcy…</div></ha-card>`,
      );
      this.shadowRoot.getElementById("refresh").onclick = () => this.load(true);
    }
    if (this._key !== `${this.data.entry_id}:${this.data.revision}`) {
      this._key = `${this.data.entry_id}:${this.data.revision}`;
      this.days.clear();
      this.load();
    }
  }
  async load(force = false) {
    const request = (this._request = (this._request || 0) + 1);
    try {
      const data = await this.call("months");
      if (request !== this._request) return;
      this.months = data.rows;
      this.draw();
      this.shadowRoot.getElementById("history-note").textContent =
        "kWh po opuście · kliknij miesiąc, aby zobaczyć dni";
      if (force) this.days.clear();
      for (const m of this.expanded) if (!this.days.has(m)) this.loadDays(m);
    } catch (e) {
      this.shadowRoot.getElementById("history-note").textContent =
        e.message || String(e);
    }
  }
  draw() {
    const rows = this.months || [];
    this.shadowRoot.getElementById("monthly-chart").innerHTML =
      chart(
        rows.map((r) => shortMonth(r.month)),
        [
          {
            name: "Pobrano",
            color: "#3287bd",
            values: rows.map((r) => r.import_kwh),
          },
          {
            name: "Oddano po opuście",
            color: "#32aaa4",
            values: rows.map((r) => r.credited_kwh),
          },
          {
            name: "Magazyn",
            color: "#7b61c4",
            axis: 1,
            values: rows.map((r) => r.balance_kwh),
          },
        ],
      ) +
      legend([
        ["Pobrano", "#3287bd"],
        ["Oddano", "#32aaa4"],
        ["Magazyn · prawa oś", "#7b61c4"],
      ]);
    this.shadowRoot.getElementById("months").innerHTML = [...rows]
      .reverse()
      .map(
        (r) =>
          `<tr class="month-row" data-month="${r.month}"><td><button aria-expanded="${this.expanded.has(r.month)}">${this.expanded.has(r.month) ? "▾" : "▸"} ${esc(month(r.month))}</button>${r.partial ? "<small>do dziś</small>" : ""}</td><td class="minus">${fmt(r.import_kwh)}</td><td class="plus">${fmt(r.credited_kwh)}</td><td class="balance">${fmt(r.balance_kwh)}</td><td>${fmt(r.net_kwh)}</td></tr>${this.expanded.has(r.month) ? `<tr><td colspan="5" class="details-cell" data-days="${r.month}">${this.dailyHTML(r.month)}</td></tr>` : ""}`,
      )
      .join("");
    for (const row of this.shadowRoot.querySelectorAll("[data-month]"))
      row.querySelector("button").onclick = () => {
        const key = row.dataset.month;
        if (this.expanded.has(key)) this.expanded.delete(key);
        else {
          this.expanded.add(key);
          if (!this.days.has(key)) this.loadDays(key);
        }
        this.draw();
      };
  }
  async loadDays(key) {
    const identity = this._key;
    try {
      const result = await this.call("daily", { month: key });
      if (identity !== this._key) return;
      this.days.set(key, result);
    } catch (e) {
      this.days.set(key, { error: e.message || String(e) });
    }
    this.draw();
  }
  dailyHTML(key) {
    const data = this.days.get(key);
    if (!data) return '<div class="empty">Wczytywanie dni…</div>';
    if (data.error) return `<div class="empty">${esc(data.error)}</div>`;
    const rows = data.rows;
    return `<div class="small-chart">${chart(
      rows.map((r) => r.day.slice(8)),
      [
        {
          name: "Pobrano",
          color: "#3287bd",
          values: rows.map((r) => r.import_kwh),
        },
        {
          name: "Oddano po opuście",
          color: "#32aaa4",
          values: rows.map((r) => r.credited_kwh),
        },
        {
          name: "Magazyn na koniec dnia",
          color: "#7b61c4",
          axis: 1,
          values: rows.map((r) => r.balance_kwh),
        },
      ],
      { height: 175 },
    )}</div><div class="daily-table"><table><thead><tr><th>Dzień</th><th>Pobrano</th><th>Oddano</th><th>Magazyn</th><th>Netto</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(day(r.day))}${r.partial ? " ·" : ""}</td><td class="minus">${fmt(r.import_kwh)}</td><td class="plus">${fmt(r.credited_kwh)}</td><td class="balance">${fmt(r.balance_kwh)}</td><td>${fmt(r.net_kwh)}</td></tr>`).join("")}</tbody></table></div>`;
  }
}
class ProjectionCard extends PGEBase {
  render() {
    const plan = this.data.planning || {},
      forecast = plan.forecast,
      inventory = plan.inventory,
      usage = this.data.comparison || [],
      rows = forecast?.rows || [];
    const first = this.data.current?.available_energy,
      balance = inventory?.balance_kwh ?? first;
    const points = usage.length
      ? usage
      : rows.map((r) => ({
          month: r.day.slice(0, 7),
          previous_kwh: null,
          current_kwh: null,
        }));
    const unknown = points.filter((r) => r.previous_kwh == null).length;
    this.frame(
      `<ha-card><div class="head"><h2>${esc(this.config.title || "Czy magazyn wystarczy?")}</h2><span class="chip">do ${esc(day(plan.target_day))}</span></div><div class="stats"><div class="stat"><small>TERAZ</small><strong>${fmt(balance == null ? null : Math.max(0, Number(balance)))}</strong><small>kWh do odbioru</small></div><div class="stat"><small>NA ROZLICZENIE</small><strong>${fmt(forecast?.balance_kwh)}</strong><small>kWh po poborze</small></div><div class="stat"><small>${forecast?.first_shortfall_day ? "WYCZERPIE SIĘ" : "WYSTARCZY DO"}</small><strong style="font-size:16px">${esc(forecast?.first_shortfall_day ? day(forecast.first_shortfall_day) : forecast?.complete ? day(plan.target_day) : "—")}</strong><small>${forecast?.complete ? "według historii" : "brak pełnej historii"}</small></div></div>${
        points.length
          ? chart(
              points.map((r) => shortMonth(r.month)),
              [
                {
                  name: "Pobór rok wcześniej",
                  color: "#90a4ae",
                  dash: true,
                  values: points.map((r) => r.previous_kwh),
                },
                {
                  name: "Pobór obecnie",
                  color: "#3287bd",
                  values: points.map((r) => r.current_kwh),
                },
                {
                  name: "Projekcja magazynu",
                  color: "#7b61c4",
                  axis: 1,
                  values: points.map(
                    (r) =>
                      rows.find((x) => x.day.slice(0, 7) === r.month)
                        ?.balance_kwh ?? null,
                  ),
                },
              ],
            )
          : '<div class="empty">Brak historii do porównania.</div>'
      }${legend([
        ["Pobór rok wcześniej", "#90a4ae"],
        ["Pobór obecnie", "#3287bd"],
        ["Magazyn · prawa oś", "#7b61c4"],
      ])}<div class="sub">Bez przyszłych doładowań · pobór jak rok wcześniej · obecny miesiąc niepełny</div>${unknown ? `<div class="warn" style="margin-top:10px">Brak historii dla ${unknown} mies. — luki pozostają puste.</div>` : ""}${plan.inventory_error ? '<div class="warn" style="margin-top:8px">Dodaj partie z faktury, aby wyznaczyć saldo i ważność.</div>' : ""}${inventory?.next_expiry ? `<div class="sub" style="margin-top:10px">Najbliższa ważność: <b>${esc(day(inventory.next_expiry))}</b></div>` : ""}<details><summary>Liczby miesiąc po miesiącu</summary><table><thead><tr><th>Miesiąc</th><th>Rok wcześniej</th><th>Obecnie</th><th>Magazyn</th></tr></thead><tbody>${points.map((r) => `<tr><td>${esc(month(r.month))}</td><td>${fmt(r.previous_kwh)}</td><td>${fmt(r.current_kwh)}</td><td class="balance">${fmt(rows.find((x) => x.day.slice(0, 7) === r.month)?.balance_kwh)}</td></tr>`).join("")}</tbody></table></details></ha-card>`,
    );
  }
}
const sourceRoles = {
  grid_power: ["Moc sieci +/−", "W"],
  battery_power: ["Moc akumulatora +/−", "W"],
  pv_power: ["Moc PV", "W"],
  home_power: ["Moc domu", "W"],
  grid_import_power: ["Moc pobierana z sieci", "W"],
  grid_export_power: ["Moc oddawana do sieci", "W"],
  battery_charge_power: ["Moc ładowania", "W"],
  battery_discharge_power: ["Moc rozładowania", "W"],
  battery_soc: ["Poziom naładowania", "%"],
  battery_stored: ["Energia w akumulatorze", "kWh"],
  pv_energy: ["Produkcja PV — licznik", "kWh"],
  home_energy: ["Zużycie domu — licznik", "kWh"],
  battery_charge_energy: ["Ładowanie — licznik", "kWh"],
  battery_discharge_energy: ["Rozładowanie — licznik", "kWh"],
};
class SettingsCard extends PGEBase {
  render() {
    if (this.shadowRoot.querySelector("dialog[open]")) return;
    const admin = this._hass?.user?.is_admin;
    this.frame(
      `<style>dialog{color:var(--primary-text-color);background:var(--card-background-color,#fff);border:0;border-radius:20px;width:min(940px,96vw);max-height:90dvh;padding:0;box-shadow:0 20px 80px #0004}dialog::backdrop{background:#14283280;backdrop-filter:blur(3px)}.dialog-head{position:sticky;top:0;background:var(--card-background-color,#fff);z-index:2;padding:16px 20px;border-bottom:1px solid var(--divider-color,#dbe5e9);display:flex;justify-content:space-between;align-items:center}.tabs{display:flex;gap:6px;padding:12px 16px}.tabs .active{color:var(--primary-color,#3287bd);background:var(--secondary-background-color,#edf5f6)}.source-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.source-grid label{display:flex;flex-direction:column;gap:6px;font-size:12px}.source-section{margin:0 0 24px}.source-section h3{margin-bottom:12px}.consumer-config{display:grid;grid-template-columns:1fr 1.3fr 1.3fr auto;gap:8px;margin:10px 0}.consumer-config input,.consumer-config select{width:100%;font-size:12px}.footer{display:flex;align-items:center;justify-content:space-between;margin-top:20px}#source-status{font-size:12px;margin-top:10px}@media(max-width:600px){.consumer-config{grid-template-columns:1fr 1fr}.source-grid{grid-template-columns:1fr}dialog{width:96vw;max-height:94dvh}}</style><ha-card><div class="head" style="margin-bottom:8px"><h2>${esc(this.config.title || "Rozliczenia i ustawienia")}</h2><ha-icon icon="mdi:tune-variant"></ha-icon></div><div class="row">${admin ? '<button id="open-sources" class="primary">Źródła energii</button><button id="open-invoices">Faktury</button><button id="open-plan">Plan i partie</button>' : '<span class="sub">Ustawienia są dostępne dla administratora.</span>'}</div></ha-card><dialog><div class="dialog-head"><h2>Magazyn PGE</h2><button id="close-dialog" aria-label="Zamknij">✕</button></div><div class="tabs"><button data-tab="sources">Źródła energii</button><button data-tab="invoices">Faktury</button><button data-tab="plan">Plan i partie</button></div><div id="settings-panel"></div><div class="sub" style="padding:12px 20px;text-align:right">Integracja ${esc(this.data.version || "—")} · Karta ${VERSION}</div></dialog>`,
    );
    if (admin)
      for (const tab of ["sources", "invoices", "plan"])
        this.shadowRoot.getElementById(`open-${tab}`).onclick = () =>
          this.open(tab);
    this.shadowRoot.getElementById("close-dialog").onclick = () =>
      this.shadowRoot.querySelector("dialog").close();
    for (const b of this.shadowRoot.querySelectorAll("[data-tab]"))
      b.onclick = () => this.tab(b.dataset.tab);
  }
  open(tab = "sources") {
    if (!this._hass.user?.is_admin) return;
    this._energyRevision = this.data.revision;
    this._sourceDraft = JSON.parse(
      JSON.stringify(
        this.data.energy?.config || { sources: {}, consumers: [] },
      ),
    );
    this.tab(tab);
    this.shadowRoot.querySelector("dialog").showModal();
  }
  tab(tab) {
    for (const b of this.shadowRoot.querySelectorAll("[data-tab]"))
      b.classList.toggle("active", b.dataset.tab === tab);
    const panel = this.shadowRoot.getElementById("settings-panel");
    if (panel.querySelector("[data-source]"))
      this._sourceDraft = this.readSources();
    if (tab === "sources") {
      this.sourcesHTML();
      return;
    }
    const settings = window.document.createElement("pge-admin-panel");
    settings.setConfig({ entry_id: this.data.entry_id, tab });
    panel.replaceChildren(settings);
    settings.hass = this._hass;
  }
  options(unit, selected) {
    const own = new Set(Object.values(this.data.entities || {}));
    const valid =
      unit === "W"
        ? ["W", "kW"]
        : unit === "kWh"
          ? ["Wh", "kWh", "MWh"]
          : ["%"];
    const ids = Object.keys(this._hass.states || {}).filter(
      (id) =>
        id.startsWith("sensor.") &&
        !own.has(id) &&
        valid.includes(this._hass.states[id].attributes?.unit_of_measurement),
    );
    if (selected && !ids.includes(selected)) ids.push(selected);
    ids.sort((a, b) =>
      (this._hass.states[a]?.attributes?.friendly_name || a).localeCompare(
        this._hass.states[b]?.attributes?.friendly_name || b,
        "pl",
      ),
    );
    return `<option value="">Nie podłączono</option>${ids.map((id) => `<option value="${esc(id)}" ${id === selected ? "selected" : ""}>${esc(this._hass.states[id]?.attributes?.friendly_name || id)} (${esc(id)})</option>`).join("")}`;
  }
  readSources() {
    const root = this.shadowRoot;
    return {
      directions: Object.fromEntries(
        [...root.querySelectorAll("[data-direction]")].map((input) => [
          input.dataset.direction,
          input.value,
        ]),
      ),
      sources: Object.fromEntries(
        [...root.querySelectorAll("[data-source]")]
          .filter((s) => s.value)
          .map((s) => [s.dataset.source, s.value]),
      ),
      consumers: [...root.querySelectorAll(".consumer-config")]
        .map((row) => ({
          name: row.querySelector("input").value,
          power: row.querySelector("[data-power]").value,
          energy: row.querySelector("[data-energy]").value,
        }))
        .filter((c) => c.name || c.power || c.energy),
    };
  }
  sourcesHTML() {
    const config = this._sourceDraft;
    const field = (key) => {
      const [title, unit] = sourceRoles[key];
      return `<label>${title}<select data-source="${key}">${this.options(unit, config.sources[key])}</select></label>`;
    };
    this.shadowRoot.getElementById("settings-panel").innerHTML =
      `<div style="padding:8px 20px 24px"><div class="source-section"><h3>Panele słoneczne i dom</h3><div class="source-grid">${["pv_power", "pv_energy", "home_power", "home_energy"].map(field).join("")}</div></div><div class="source-section"><h3>Sieć</h3><div class="sub" style="margin-bottom:10px">Liczniki importu i eksportu są już wybrane w integracji. Tu podłączasz opcjonalną moc chwilową.</div><div class="source-grid">${["grid_power", "grid_import_power", "grid_export_power"].map(field).join("")}</div></div><div class="source-section"><h3>Lokalny akumulator</h3><div class="source-grid">${["battery_soc", "battery_stored", "battery_power", "battery_charge_power", "battery_discharge_power", "battery_charge_energy", "battery_discharge_energy"].map(field).join("")}</div></div><div class="source-grid" style="margin-bottom:16px"><label>Dodatnia moc sieci oznacza<select data-direction="grid"><option value="import" ${config.directions?.grid !== "export" ? "selected" : ""}>Pobór z sieci</option><option value="export" ${config.directions?.grid === "export" ? "selected" : ""}>Oddawanie do sieci</option></select></label><label>Dodatnia moc akumulatora oznacza<select data-direction="battery"><option value="charge" ${config.directions?.battery !== "discharge" ? "selected" : ""}>Ładowanie</option><option value="discharge" ${config.directions?.battery === "discharge" ? "selected" : ""}>Rozładowanie</option></select></label></div><div class="sub">Moc: W / kW. Dla sieci i akumulatora wybierz jeden sensor +/− albo dwa oddzielne kierunki. Liczniki: narastająca energia Wh / kWh / MWh bez resetów. Brak odczytu pozostanie pusty.</div><div class="source-section" style="margin-top:24px"><h3>Odbiorcy w domu</h3><div class="sub">Nazwa · moc teraz · narastający licznik energii. Nie sumujemy odbiorców do zużycia domu.</div>${config.consumers.map((c, i) => `<div class="consumer-config"><input aria-label="Nazwa odbiorcy" placeholder="np. Pompa ciepła" value="${esc(c.name)}"><select data-power aria-label="Moc odbiorcy">${this.options("W", c.power)}</select><select data-energy aria-label="Licznik odbiorcy">${this.options("kWh", c.energy)}</select><button data-remove="${i}" aria-label="Usuń odbiorcę">✕</button></div>`).join("")}<button id="add-consumer">＋ Dodaj odbiorcę</button></div><div class="footer"><button id="save-sources" class="primary">Zapisz źródła</button><span class="sub">Działa bez restartu HA</span></div><div id="source-status" role="status"></div></div>`;
    this.shadowRoot.getElementById("add-consumer").onclick = () => {
      this._sourceDraft = this.readSources();
      if (this._sourceDraft.consumers.length < 16)
        this._sourceDraft.consumers.push({ name: "", power: "", energy: "" });
      this.sourcesHTML();
    };
    for (const b of this.shadowRoot.querySelectorAll("[data-remove]"))
      b.onclick = () => {
        this._sourceDraft = this.readSources();
        this._sourceDraft.consumers.splice(Number(b.dataset.remove), 1);
        this.sourcesHTML();
      };
    this.shadowRoot.getElementById("save-sources").onclick = () =>
      this.saveSources();
  }
  async saveSources() {
    const status = this.shadowRoot.getElementById("source-status"),
      button = this.shadowRoot.getElementById("save-sources");
    button.disabled = true;
    try {
      const config = this.readSources();
      await this.call("put_energy", { revision: this._energyRevision, config });
      this._energyRevision = this.data.revision;
      this._sourceDraft = config;
      status.textContent =
        "Źródła zapisane. Karty i encje zostały zaktualizowane.";
      status.className = "";
    } catch (e) {
      status.textContent = e.message || String(e);
      status.className = "error";
    } finally {
      button.disabled = false;
    }
  }
}
class Dashboard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.config = {};
  }
  setConfig(config) {
    this.config = config;
    this.build();
  }
  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot.querySelector("pge-energy-card")) this.build();
    for (const card of this.shadowRoot.querySelectorAll("[data-module]"))
      card.hass = hass;
  }
  getCardSize() {
    return 16;
  }
  getGridOptions() {
    return { columns: "full", rows: "auto" };
  }
  build() {
    this.shadowRoot.innerHTML = `<style>:host{display:block}.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:16px;max-width:1400px;margin:auto}.stack{display:grid;gap:16px;align-content:start}.tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.wide{grid-column:1/-1}@media(max-width:850px){.layout{grid-template-columns:minmax(0,1fr)}}@media(max-width:420px){.tiles{gap:6px}}</style><div class="layout"><div class="stack"><pge-energy-card data-module></pge-energy-card><pge-settings-card data-module></pge-settings-card></div><div class="stack"><div class="tiles">${["available_energy", "deficit", "period_balance"].map((key) => `<pge-balance-card data-module data-metric="${key}"></pge-balance-card>`).join("")}</div><pge-projection-card data-module></pge-projection-card></div><pge-history-card class="wide" data-module></pge-history-card></div>`;
    for (const card of this.shadowRoot.querySelectorAll("[data-module]")) {
      card.setConfig({
        ...(this.config.entry_id ? { entry_id: this.config.entry_id } : {}),
        ...(card.dataset.metric ? { metric: card.dataset.metric } : {}),
      });
      if (this._hass) card.hass = this._hass;
    }
  }
}
class CardEditor extends HTMLElement {
  setConfig(config) {
    this.config = config;
    this.render();
  }
  set hass(hass) {
    this._hass = hass;
  }
  render() {
    this.innerHTML = `<style>pge-card-editor label{display:flex;flex-direction:column;gap:8px;margin:16px 0}pge-card-editor input,pge-card-editor select{padding:10px;font:inherit}</style><label>Tytuł<input data-key="title" value="${esc(this.config.title)}"></label><label>Identyfikator integracji (puste przy jednej)<input data-key="entry_id" value="${esc(this.config.entry_id)}"></label>${
      this.config.type === "custom:pge-balance-card"
        ? `<label>Wartość<select data-key="metric">${Object.entries(coreMetrics)
            .map(
              ([key, [name]]) =>
                `<option value="${key}" ${key === (this.config.metric || "available_energy") ? "selected" : ""}>${name}</option>`,
            )
            .join("")}</select></label>`
        : ""
    }`;
    for (const input of this.querySelectorAll("[data-key]"))
      input.onchange = () => {
        const config = { ...this.config, [input.dataset.key]: input.value };
        this.config = config;
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config },
            bubbles: true,
            composed: true,
          }),
        );
      };
  }
}
for (const [tag, element] of [
  ["pge-energy-card", EnergyCard],
  ["pge-balance-card", BalanceCard],
  ["pge-history-card", HistoryCard],
  ["pge-projection-card", ProjectionCard],
  ["pge-settings-card", SettingsCard],
  ["pge-storage-card", Dashboard],
  ["pge-card-editor", CardEditor],
])
  if (!customElements.get(tag)) customElements.define(tag, element);
window.customCards = window.customCards || [];
for (const [type, name, description] of [
  [
    "pge-energy-card",
    "PGE · Energia w domu",
    "PV, dom, sieć, lokalny akumulator i magazyn PGE",
  ],
  [
    "pge-balance-card",
    "PGE · Pojedynczy kafelek",
    "Magazyn, niedobór lub zmiana od faktury",
  ],
  [
    "pge-history-card",
    "PGE · Miesiące i dni",
    "Rozliczenie po opuście, tabela i wykres",
  ],
  [
    "pge-projection-card",
    "PGE · Projekcja magazynu",
    "Pobór rok wcześniej, obecnie i zapas do rozliczenia",
  ],
  [
    "pge-settings-card",
    "PGE · Konfigurator",
    "Źródła energii i faktury w osobnym oknie",
  ],
  ["pge-storage-card", "PGE · Gotowy dashboard", "Zestaw oddzielnych modułów"],
])
  if (!window.customCards.some((c) => c.type === type))
    window.customCards.push({ type, name, description, preview: true });
