/* PGE 0.13.0: independent Lovelace modules, no external libraries. */
import "./pge-settings.js?v=0.13.0";
const VERSION = "0.13.0";
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
  opust_deduction: ["Potrącenie opustu", "mdi:percent-outline", "#bd6639"],
  period_balance: ["Zmiana od faktury", "mdi:swap-vertical", "#278680"],
  carried_balance: [
    "Po ostatniej fakturze",
    "mdi:file-document-outline",
    "#607d8b",
  ],
  import_since_settlement: ["Pobrano od faktury", "mdi:arrow-down", "#3287bd"],
  credited_since_settlement: ["Oddano od faktury", "mdi:arrow-up", "#ab63b4"],
};
const css = `:host{display:block;min-width:0;container-type:inline-size;-webkit-user-select:text;user-select:text;--pge-blue:#3287bd;--pge-teal:#278680;--pge-purple:#7b61c4;--pge-orange:#e6a020}*{box-sizing:border-box}ha-card{padding:20px;border-radius:20px;overflow:hidden;color:var(--primary-text-color,#24333c)}h2{font-size:17px;margin:0;font-weight:650}h3{font-size:14px;margin:0}.head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;margin-bottom:16px}.sub{font-size:12px;color:var(--secondary-text-color,#6a7c87);line-height:1.5}.chip{font-size:11px;padding:5px 9px;border-radius:20px;background:var(--secondary-background-color,#f1f5f6);white-space:nowrap}.row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.seg{display:flex;background:var(--secondary-background-color,#f1f5f6);border-radius:20px;padding:3px}.seg button{border-radius:16px;padding:6px 12px;font-size:12px}.seg .active{background:var(--card-background-color,#fff);box-shadow:0 1px 4px #0002}button{font:inherit;color:inherit;background:transparent;border:0;cursor:pointer;padding:8px;border-radius:8px}button:hover{background:var(--secondary-background-color,#f0f4f5)}button:focus-visible,summary:focus-visible{outline:2px solid var(--primary-color,#3287bd);outline-offset:2px}.primary{background:var(--primary-color,#3287bd);color:white;padding:10px 16px}.primary:hover{filter:brightness(.94);background:var(--primary-color,#3287bd)}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}th,td{text-align:right;border-bottom:1px solid var(--divider-color,#e7edef);padding:10px 6px;white-space:nowrap}th{font-size:10px;color:var(--secondary-text-color,#667b85);font-weight:500}th:first-child,td:first-child{text-align:left}td small{display:block;font-size:10px;color:var(--secondary-text-color)}td.balance{font-weight:700}td.plus{color:var(--pge-teal)}td.minus{color:var(--pge-blue)}.month-row{cursor:pointer}.month-row:hover{background:var(--secondary-background-color,#f5f8f8)}.month-row button{padding:0;font-weight:600}.details-cell{padding:0 0 14px;background:var(--secondary-background-color,#f5f8f8)}.details-cell table{font-size:11px}.daily-table{max-height:330px;overflow:auto}.daily-table thead{position:sticky;top:0;background:var(--card-background-color,#fff);z-index:1}.details-cell td,.details-cell th{padding:7px 6px}.small-chart{padding:12px 4px 0}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--secondary-text-color);margin:12px 0}.legend span{display:flex;align-items:center;gap:5px}.dot{height:7px;width:15px;border-radius:5px;background:var(--c)}svg.chart{width:100%;height:auto;max-height:240px;display:block;overflow:visible}svg.chart text{fill:var(--secondary-text-color,#647985);font-size:13px}svg.chart .grid{stroke:var(--divider-color,#e0e8eb);stroke-dasharray:3 4}.empty{font-size:12px;color:var(--secondary-text-color);padding:12px 0}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0 16px}.stat{background:var(--secondary-background-color,#f4f7f8);border-radius:12px;padding:12px 10px}.stat strong{display:block;font-size:clamp(16px,5cqw,24px);overflow-wrap:anywhere;margin:4px 0}.stat small{font-size:10px;color:var(--secondary-text-color)}details>summary{cursor:pointer;font-size:12px;color:var(--secondary-text-color);padding:10px 0}ha-icon{--mdc-icon-size:22px}select,input{font:inherit;background:var(--card-background-color,#fff);color:var(--primary-text-color);border:1px solid var(--divider-color,#dbe3e7);padding:10px;border-radius:9px;max-width:100%}.warn{color:#b45a2d;font-size:12px}.error{color:var(--error-color,#b3261e)}@media(max-width:450px){ha-card{padding:16px 12px}th,td{padding:9px 4px}.stat{padding:9px 7px}.stat strong{font-size:18px}.head{gap:6px}.legend{gap:9px;font-size:10px}}`;
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
    const template = window.document.createElement("template");
    template.innerHTML = `<style>${css}</style>${this.data?.error ? `<ha-card><div class="error">${esc(this.data.error)}</div></ha-card>` : content}`;
    if (this.localName === "pge-settings-card" || this.localName === "pge-admin-panel") {
      this.shadowRoot.innerHTML = template.innerHTML;
      return;
    }
    // Keep the card and its layout boxes mounted during live power updates.
    const patch = (parent, next) => {
      for (let i = 0; i < next.childNodes.length; i++) {
        const fresh = next.childNodes[i], old = parent.childNodes[i];
        if (!old) { parent.appendChild(fresh.cloneNode(true)); continue; }
        if (old.nodeType !== fresh.nodeType || old.nodeName !== fresh.nodeName) {
          old.replaceWith(fresh.cloneNode(true)); continue;
        }
        if (fresh.nodeType === 3) {
          if (old.textContent !== fresh.textContent) old.textContent = fresh.textContent;
        } else if (fresh.nodeType === 1) {
          for (const attr of [...old.attributes])
            if (!fresh.hasAttribute(attr.name)) old.removeAttribute(attr.name);
          for (const attr of fresh.attributes)
            if (old.getAttribute(attr.name) !== attr.value) old.setAttribute(attr.name, attr.value);
          patch(old, fresh);
        }
      }
      while (parent.childNodes.length > next.childNodes.length) parent.lastChild.remove();
    };
    patch(this.shadowRoot, template.content);
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
    return { columns: 4, rows: 2, min_columns: 4 };
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
    let value = key === "opust_deduction" ? current.opust_deduction_since_settlement_kwh : current[key] ?? current[`${key}_kwh`];
    if (inventory && key === "available_energy")
      value = Math.max(0, Number(inventory.balance_kwh));
    if (inventory && key === "deficit")
      value = Math.max(0, -Number(inventory.balance_kwh));
    this.frame(
      `<ha-card style="padding:16px"><button id="metric" style="width:100%;text-align:left;padding:0"><div class="row"><ha-icon icon="${icon}" style="color:${color};background:${color}15;border-radius:12px;padding:10px;box-sizing:content-box"></ha-icon><span class="sub">${esc(this.config.title || title)}</span></div><div style="font-size:clamp(22px,7cqw,32px);font-weight:700;margin-top:14px;white-space:nowrap">${fmt(value)} <small style="font-size:14px;font-weight:400">kWh</small></div></button></ha-card>`,
    );
    this.shadowRoot.getElementById("metric").onclick = () => this.info(key);
  }
}
const precise = (value) =>
  value == null || !Number.isFinite(Number(value))
    ? "—"
    : new Intl.NumberFormat("pl-PL", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      }).format(Math.abs(Number(value)) < 0.05 ? 0 : Number(value));
const signedPower = value => value == null ? "—" : `${Number(value) > 0 ? "+" : ""}${fmt(value)}`;
const signed = (value) =>
  value == null ? "—" : `${Number(value) > 0 ? "+" : ""}${precise(value)}`;
const localDay = () =>
  new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Warsaw",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
const periodCache = new WeakMap();
const shiftedDay = (anchor, kind, step) => {
  const [y, m, d] = anchor.split("-").map(Number),
    date = new Date(Date.UTC(y, m - 1, d));
  if (kind === "day" || kind === "week")
    date.setUTCDate(d + step * (kind === "week" ? 7 : 1));
  else if (kind === "month") {
    date.setUTCDate(1);
    date.setUTCMonth(m - 1 + step);
  } else {
    date.setUTCMonth(0, 1);
    date.setUTCFullYear(y + step);
  }
  return date.toISOString().slice(0, 10);
};
class PeriodCard extends PGEBase {
  constructor() {
    super();
    this.period = "day";
    this.anchor = localDay();
    this.periodData = null;
    this._expanded = new Set();
  }
  periodValues() {
    return (
      this.periodData?.values ||
      (this.period === "day" && this.anchor === localDay()
        ? this.data.energy?.today || {}
        : {})
    );
  }
  ensurePeriod() {
    if (!this.data?.entry_id || !this._hass) return;
    const key = `${this.data.entry_id}:${this.data.revision}:${this.data.hourly_revision || 0}:${this.period}:${this.anchor}:${Math.floor(Date.now() / 300000)}`;
    if (this._periodKey === key) return;
    this._periodKey = key;
    this._periodError = null;
    let cache = periodCache.get(this._hass.connection);
    if (!cache) periodCache.set(this._hass.connection, (cache = new Map()));
    let request = cache.get(key);
    if (!request) {
      request = this.call("energy_period", {
        period: this.period,
        anchor_day: this.anchor,
      });
      cache.set(key, request);
      if (cache.size > 48) cache.delete(cache.keys().next().value);
      request.catch(() => cache.delete(key));
    }
    request
      .then((result) => {
        if (this._periodKey !== key) return;
        this.periodData = result;
        this.render();
      })
      .catch((error) => {
        if (this._periodKey !== key) return;
        this._periodError = error.message || String(error);
        this.render();
      });
  }
  periodHTML() {
    const label =
      this.periodData?.label ||
      (this.period === "day"
        ? day(this.anchor)
        : month(this.anchor.slice(0, 7)));
    return `<div class="period-picker"><div class="period-tabs">${[
      ["day", "Dzień"],
      ["week", "Tydzień"],
      ["month", "Miesiąc"],
      ["year", "Rok"],
    ]
      .map(
        ([key, label]) =>
          `<button data-period="${key}" class="${this.period === key ? "active" : ""}" aria-pressed="${this.period === key}">${label}</button>`,
      )
      .join(
        "",
      )}</div><div class="period-nav"><button data-shift="-1" aria-label="Poprzedni okres">‹</button><label><span>${esc(label)}</span><input data-anchor type="date" aria-label="Wybierz datę okresu" value="${this.anchor}" max="${localDay()}"></label><button data-shift="1" aria-label="Następny okres" ${shiftedDay(this.anchor, this.period, 1) > localDay() ? "disabled" : ""}>›</button><button data-current title="Bieżący okres">↺</button></div></div>`;
  }
  bindPeriod() {
    for (const button of this.shadowRoot.querySelectorAll("[data-period]"))
      button.onclick = () => {
        this.period = button.dataset.period;
        this.changePeriod();
      };
    for (const button of this.shadowRoot.querySelectorAll("[data-shift]"))
      button.onclick = () => {
        const next = shiftedDay(
          this.anchor,
          this.period,
          Number(button.dataset.shift),
        );
        if (next <= localDay()) {
          this.anchor = next;
          this.changePeriod();
        }
      };
    this.shadowRoot.querySelector("[data-current]").onclick = () => {
      this.anchor = localDay();
      this.changePeriod();
    };
    this.shadowRoot.querySelector("[data-anchor]").onchange = (event) => {
      const value = event.target.value;
      if (/^\d{4}-\d{2}-\d{2}$/.test(value) && value <= localDay()) {
        this.anchor = value;
        this.changePeriod();
      }
    };
  }
  changePeriod() {
    this._periodKey = null;
    this.periodData = null;
    this.render();
  }
}
const periodCSS = `.period-picker{margin:8px 0 18px}.period-tabs{display:flex;gap:4px;padding:4px;border-radius:13px;background:var(--secondary-background-color,#f3f6f7)}.period-tabs button{flex:1;font-size:12px;padding:8px 4px}.period-tabs button.active{background:var(--card-background-color,#fff);box-shadow:0 1px 5px #0001}.period-nav{display:flex;justify-content:center;align-items:center;gap:8px;margin-top:9px;font-size:12px}.period-nav>button{font-size:22px;padding:3px 12px}.period-nav button:disabled{opacity:.25;cursor:default}.period-nav label{position:relative;min-width:120px;text-align:center;font-weight:600}.period-nav input{position:absolute;inset:0;opacity:0;width:100%;cursor:pointer;padding:0}.period-note{font-size:11px;color:var(--secondary-text-color);text-align:center;line-height:1.5;margin-top:10px}`;
class EnergyCard extends PeriodCard {
  constructor() {
    super();
    this.flowAverageSeconds = 10;
  }
  setConfig(config) {
    this.flowAverageSeconds = [1,5,10,15].includes(Number(config.average_seconds)) ? Number(config.average_seconds) : 10;
    super.setConfig(config);
  }
  render() {
    this.ensurePeriod();
    const frame = this.data.energy?.diagram_frame,
      e = frame?.energy || this.data.energy || { values: {}, today: {} },
      powerWindow = e.power_windows?.[String(this.flowAverageSeconds)],
      v = powerWindow?.covered_seconds >= this.flowAverageSeconds
        ? { ...e.values, ...powerWindow.values } : e.values;
    const viewKey = `${this.data.revision}:${this.period}:${this.anchor}:${this.flowAverageSeconds}`;
    if (this._displayFrame !== frame?.sequence || this._displayKey !== viewKey || !this._displayPeriodData) {
      this._displayFrame = frame?.sequence;
      this._displayKey = viewKey;
      this._displayPeriodData = this.periodData;
    }
    const t = this._displayPeriodData?.values || (this.period === "day" && this.anchor === localDay() ? e.today || {} : {});
    const currentHour = this.data.energy?.hourly_current || this.data.hourly?.current;
    const hourValue = value => value == null ? "—" : `${Number(value) > 0 ? "+" : ""}${new Intl.NumberFormat("pl-PL", {maximumFractionDigits:3}).format(Number(value))}`;
    const showHour = this.config.show_hour ?? this.data.energy?.config?.show_hour ?? true;
    const hourHTML = showHour && currentHour ? `<button class="hour-buffer" data-hour-info aria-label="Szczegóły bieżącej godziny" title="Bieżąca godzina: plus pobór, minus oddawanie. Kliknij szczegóły."><span>Bieżąca<br>godzina</span><strong>${hourValue(currentHour.balance_kwh)}</strong><small>kWh</small></button>` : "";
    const net = (a, b) =>
        a == null || b == null ? null : Number(a) - Number(b),
      grid = net(v.grid_import_power, v.grid_export_power),
      battery = net(v.battery_charge_power, v.battery_discharge_power),
      available =
        frame ? frame.available_energy : this.data.planning?.inventory?.balance_kwh ?? this.data.current?.available_energy;
    const pgeCredit =
        (this.period === "day" && this.anchor === localDay() && frame ? e.today.pge_credited_energy : t.pge_credited_energy) ??
        (this.period === "day" && this.anchor === localDay()
          ? t.credited_energy
          : null),
      pgeDraw = this.period === "day" && this.anchor === localDay() && frame
        ? e.today.pge_withdrawn_energy : t.pge_withdrawn_energy;
    const order = this.data.energy?.config?.pv_order?.length ? this.data.energy.config.pv_order : [...(e.pv_arrays || [])].map(a=>a.power_entity).reverse();
    const pvArrays = [...(e.pv_arrays || [])].sort((a,b) => { const rank = x => order.indexOf(x.power_entity) < 0 ? 999 : order.indexOf(x.power_entity); return rank(a)-rank(b); }).map(array => ({...array,
      power_w: powerWindow?.covered_seconds >= this.flowAverageSeconds
        ? powerWindow.pv_arrays?.[array.id] ?? array.power_w : array.power_w}));
    const nodes = [
      {
        key: "pv",
        name: "Słońce",
        icon: "mdi:solar-power",
        x: 65,
        y: 17,
        color: "#dd9a1a",
        value: v.pv_power,
        unit: "W",
        energy: t.pv_energy,
        entity: "pv_power",
      },
      {
        key: "grid",
        name: "Sieć",
        icon: "mdi:transmission-tower",
        x: 25,
        y: 50,
        color: "#3287bd",
        value: grid,
        unit: "W",
        energy: net(t.grid_import_energy, t.grid_export_energy),
        signed: true,
        entity: "grid_power",
        title: `+ pobieranie / − oddawanie. Pobór ${precise(t.grid_import_energy)} kWh; oddano ${precise(t.grid_export_energy)} kWh`,
      },
      {
        key: "home",
        name: "Dom",
        icon: "mdi:home",
        x: 65,
        y: 50,
        color: "#278680",
        value: v.home_power,
        unit: "W",
        energy: t.home_energy,
        entity: "home_power",
      },
      {
        key: "pge",
        name: "Magazyn PGE",
        icon: "mdi:cloud-outline",
        x: 25,
        y: 83,
        color: "#7b61c4",
        value: available == null ? null : Math.max(0, Number(available)),
        unit: "kWh",
        credit: pgeCredit,
        draw: pgeDraw,
        entity: "available_energy",
      },
      {
        key: "battery",
        name: "Akumulator",
        icon: "mdi:battery",
        x: 65,
        y: 83,
        color: "#32aaa4",
        value: battery,
        unit: "W",
        credit: t.battery_charge_energy,
        draw: t.battery_discharge_energy,
        soc: v.battery_soc,
        signed: true,
        entity: "battery_power",
        title: "+ ładowanie / − rozładowanie",
      },
    ];
    const arrow = (name, color, path, value) =>
      `<path class="flow-line" data-flow="${name}" d="${path}" stroke="${color}" opacity="${value ? 1 : 0.22}" ${value > 0 ? `marker-end="url(#arrow-${name})"` : value < 0 ? `marker-start="url(#arrow-${name})"` : ""}/>`;
    const defs = [
      ["pv", "#dd9a1a"],
      ["grid", "#3287bd"],
      ["battery", "#32aaa4"],
      ["pge", "#7b61c4"],
    ]
      .map(
        ([key, color]) =>
          `<marker id="arrow-${key}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M1 1L9 5L1 9Z" fill="${color}"/></marker>`,
      )
      .join("");
    const arrayList = (parity) =>
      pvArrays
        .map((a, i) => ({ a, i }))
        .filter(() => parity === 0)
        .map(
          ({ a, i }) =>
            `<button class="pv-installation" data-pv="${i}" title="${esc(a.name)}"><span>${esc(a.name)}</span><strong>${fmt(a.power_w)} W</strong></button>`,
        )
        .join("");
    const ring = key => {
      if (!["home", "battery"].includes(key) || (key === "home" && !(Number(v.home_power)>0))) return "";
      const pv = Math.max(0,Number(v.pv_power)||0), grid = Math.max(0,Number(v.grid_import_power)||0), battery = key === "home" ? Math.max(0,Number(v.battery_discharge_power)||0) : 0;
      if (key === "battery" && !(Number(v.battery_charge_power)>25)) return "";
      const total = pv+grid+battery;
      if (!total) return "";
      const a = pv/total*100, b = (pv+battery)/total*100;
      return `conic-gradient(#dd9a1a 0% ${a}%,#32aaa4 ${a}% ${b}%,#3287bd ${b}% 100%)`;
    };
    const eta = this.data.energy?.battery_estimate;
    const duration = seconds => seconds == null ? "—" : seconds < 60 ? "< 1 min" : `${Math.floor(seconds/3600) ? Math.floor(seconds/3600)+" h " : ""}${Math.ceil(seconds%3600/60)} min`;
    const range = seconds => seconds ? `${duration(seconds[0])} – ${duration(seconds[1])}` : "—";
    const etaHTML = eta && eta.quality !== "disabled" ? `<div class="battery-eta"><div><small>Do 100%</small><b>${duration(eta.charge_seconds)}</b></div><div><small>Do minimum ${eta.minimum_soc == null ? "—" : fmt(eta.minimum_soc)}%</small><b>${duration(eta.discharge_seconds)}</b></div><div><small>Zapas baterii</small><b>${precise(v.battery_stored)} kWh</b></div>${eta.model_range_seconds ? `<small class="eta-model">Profil ładowania: ${range(eta.model_range_seconds)}</small>` : ""}${eta.forecast_range_seconds ? `<small class="eta-model">Scenariusz PV: ${range(eta.forecast_range_seconds)}</small>` : ""}<small class="eta-model">Średnia ${eta.average_minutes} min · ${eta.quality === "missing_soc_or_capacity" ? "uzupełnij SOC i pojemność" : eta.quality === "collecting" ? "zbieranie pomiarów / brak przepływu" : "przy obecnym tempie"}${this.data.energy.config?.battery_forecast?.learn ? ` · profil BMS: ${eta.learned_bins}/20 zakresów` : ""}</small></div>` : "";
    this.frame(
      `<style>${periodCSS}.hour-buffer{position:absolute;left:45%;top:50%;transform:translate(-50%,-50%);width:12cqw;padding:5px 1px;border:1px solid var(--divider-color,#dce5e8);border-radius:10px;background:var(--card-background-color,#fff);z-index:2;display:grid;text-align:center;gap:2px;font-size:clamp(8px,2cqw,11px)}.hour-buffer strong{font-size:clamp(10px,2.7cqw,15px);white-space:nowrap}.hour-buffer small{font-size:9px}.node.ring{border:4px solid transparent;background:linear-gradient(var(--card-background-color,#fff),var(--card-background-color,#fff)) padding-box,var(--ring) border-box!important}.battery-eta{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px;padding:12px;border-radius:12px;background:var(--secondary-background-color,#f3f6f7);font-size:12px}.battery-eta b,.battery-eta small{display:block}.battery-eta small{font-size:10px;color:var(--secondary-text-color)}.eta-model{grid-column:1/-1}.flow-average{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--secondary-text-color);white-space:nowrap}.flow-average select{width:auto;min-width:63px;padding:5px;border-radius:8px}.flow-map{position:relative;container-type:inline-size;aspect-ratio:600/580;max-width:660px;margin:0 auto}.flow-map svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.flow-line{fill:none;stroke-width:3}[data-flow="pge"]{stroke-dasharray:4 5}.node{position:absolute;transform:translate(-50%,-50%);padding:0;width:27cqw;height:27cqw;border:2px solid var(--c);border-radius:50%;background:var(--card-background-color,#fff)!important;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;box-shadow:0 3px 16px #00000005}.node ha-icon{--mdc-icon-size:clamp(14px,3.8cqw,22px);color:var(--c)}.node .node-name{font-size:clamp(9px,2.7cqw,13px);color:var(--secondary-text-color);line-height:1.1}.node strong{font-size:clamp(13px,4.1cqw,25px);line-height:1.2;white-space:nowrap}.node .node-energy{font-size:clamp(10px,3cqw,16px);color:var(--secondary-text-color);white-space:nowrap}.node-home{border-width:3px}.node-pge strong{font-size:clamp(12px,3.8cqw,23px)}.flow-small{font-size:clamp(9px,2.5cqw,13px);white-space:nowrap}.soc{display:flex;align-items:center;gap:3px;font-size:clamp(10px,2.7cqw,14px);color:var(--c)}.soc ha-icon{--mdc-icon-size:clamp(11px,3cqw,17px)}.pv-installations{position:absolute;top:3%;width:35%;max-height:40cqw;overflow:auto;display:grid;gap:7px}.pv-left{left:0;top:0}.pv-right{right:0}.pv-installation{padding:7px 8px;background:var(--secondary-background-color,#f5f7f8);border-radius:11px;text-align:left;min-width:0}.pv-installation span{display:block;font-size:clamp(9px,2.5cqw,12px);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pv-installation strong{font-size:clamp(11px,3.2cqw,17px)}.battery-stock{position:absolute;bottom:0;left:51%;right:21%;text-align:center;font-size:11px;color:var(--secondary-text-color)}@container(max-width:380px){.node{gap:2px}.pv-installation{padding:5px}.flow-small{font-size:9px}}</style><ha-card><div class="head"><h2>${esc(this.config.title || "Energia w domu")}</h2><label class="flow-average" title="Długość średniej mocy; częstotliwość odświeżania pozostaje niezależna">Średnia<select data-flow-average aria-label="Średnia mocy diagramu">${[1,5,10,15].map(n => `<option value="${n}" ${this.flowAverageSeconds === n ? "selected" : ""}>${n} s</option>`).join("")}</select></label></div>${this.periodHTML()}${this.data.accounting_error || this.data.pending_error ? `<div class="warn">${esc(this.data.accounting_error || this.data.pending_error)}</div>` : ""}<div class="flow-map">${hourHTML}<svg viewBox="0 0 600 580" aria-hidden="true"><defs>${defs}</defs>${arrow("pv", "#dd9a1a", "M390 180V209", Number(v.pv_power))}${arrow("grid", "#3287bd", "M235 290H305", Number(grid))}${arrow("battery", "#32aaa4", "M390 375V398", Number(battery))}<path class="flow-line" data-flow="pge" d="M150 375V398" stroke="#7b61c4" opacity="0.6"/></svg><div class="pv-installations pv-left">${arrayList(0)}</div><div class="pv-installations pv-right">${arrayList(1)}</div>${nodes.map((n) => `<button class="node node-${n.key} ${ring(n.key) ? "ring" : ""}" data-entity="${n.entity}" style="left:${n.x}%;top:${n.y}%;--c:${n.color};${ring(n.key) ? `--ring:${ring(n.key)}` : ""}" title="${esc(n.title || n.name)}${ring(n.key) ? " · Szacowany udział mocy: PV żółty, akumulator turkusowy, sieć niebieski; proporcjonalny podział wspólnego zasilania" : ""}">${n.key === "battery" ? `<span class="soc"><ha-icon icon="${n.icon}"></ha-icon>${fmt(n.soc)}%</span>` : `<ha-icon icon="${n.icon}"></ha-icon>`}<span class="node-name">${n.name}</span><strong>${n.signed ? signedPower(n.value) : fmt(n.value)} ${n.unit}</strong>${n.key === "grid" ? `<span class="flow-small">Pobrano ${precise(t.grid_import_energy)} kWh</span><span class="flow-small">Oddano ${precise(t.grid_export_energy)} kWh</span>` : n.key === "pge" || n.key === "battery" ? `<span class="flow-small" title="${n.key === "pge" ? "Wprowadzone po opuście" : "Władowano"}">↓ ${precise(n.credit)} kWh</span><span class="flow-small" title="${n.key === "pge" ? "Pobrano z magazynu" : "Wyładowano"}">↑ ${precise(n.draw)} kWh</span>` : `<span class="node-energy">${n.signed ? signed(n.energy) : precise(n.energy)} kWh</span>`}</button>`).join("")}</div>${etaHTML}${this._periodError ? `<div class="warn">${esc(this._periodError)}</div>` : ""}</ha-card>`,
    );
    this.bindPeriod();
    const hourInfo = this.shadowRoot.querySelector("[data-hour-info]");
    if (hourInfo) hourInfo.onclick = () => this.info("hourly_balance");
    this.shadowRoot.querySelector("[data-flow-average]").onchange = event => {
      this.flowAverageSeconds = Number(event.target.value); this.render();
    };
    for (const button of this.shadowRoot.querySelectorAll("[data-entity]"))
      button.onclick = () => this.info(button.dataset.entity);
    for (const button of this.shadowRoot.querySelectorAll("[data-pv]"))
      button.onclick = () => {
        const entity = pvArrays[Number(button.dataset.pv)].power_entity;
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
class HourCard extends PGEBase {
  render() {
    const hour = this.data.energy?.hourly_current;
    this.frame(`<ha-card><div class="head"><h2>${esc(this.config.title || "Bieżąca godzina")}</h2></div><button data-hour-info style="font-size:28px;font-weight:700">${hour?.balance_kwh == null ? "—" : new Intl.NumberFormat("pl-PL",{maximumFractionDigits:3,signDisplay:"exceptZero"}).format(Number(hour.balance_kwh))} kWh</button><div class="sub">${hour?.known ? Number(hour.balance_kwh)>0 ? "Przewaga poboru" : Number(hour.balance_kwh)<0 ? "Przewaga oddawania" : "Zbilansowana" : "Brak odczytów"}</div></ha-card>`);
    this.shadowRoot.querySelector("[data-hour-info]").onclick = () => this.info("hourly_balance");
  }
}
class OpustCard extends PeriodCard {
  render() {
    this.ensurePeriod();
    const value = this.periodData?.values?.pge_opust_deduction_energy;
    this.frame(`<style>${periodCSS}</style><ha-card><div class="head"><h2>${esc(this.config.title || "Potrącenie opustu")}</h2></div>${this.periodHTML()}<button data-opust style="font-size:28px;font-weight:700">${precise(value)} kWh</button><div class="sub">20% nadwyżek po bilansowaniu zamkniętych godzin</div></ha-card>`);
    this.bindPeriod();
    this.shadowRoot.querySelector("[data-opust]").onclick=()=>this.info("opust_deduction");
  }
}
class ConsumersCard extends PeriodCard {
  constructor() {
    super();
    this.averageSeconds = 5;
    this.sortMode = "power";
    this.sortDirection = "desc";
    this._orders = new Map();
  }
  render() {
    this.ensurePeriod();
    const e = this.data.energy || { values: {}, today: {}, consumers: [] },
      t = this.periodValues(),
      periodRows = new Map(
        (this.periodData?.consumers || []).map((c) => [c.id, c]),
      ),
      items = (e.consumers || []).map((c, i) => ({
        ...c,
        id: c.id || c.statistic || c.energy || c.power || String(i),
        period_kwh: this.periodData
          ? (periodRows.get(
              c.id || c.statistic || c.energy || c.power || String(i),
            )?.period_kwh ?? null)
          : this.period === "day" && this.anchor === localDay()
            ? c.today_kwh
            : null,
      })),
      byId = new Map(items.map((c) => [c.id, c]));
    const children = new Map();
    for (const c of items) {
      const parent = byId.has(c.parent_id) ? c.parent_id : null;
      if (!children.has(parent)) children.set(parent, []);
      children.get(parent).push(c);
    }
    if (!this._treeInitialized && items.length) {
      for (const key of children.keys()) if (key) this._expanded.add(key);
      this._treeInitialized = true;
    }
    const counted = (c, metric) => {
      let parent = byId.get(c.parent_id),
        visited = new Set([c.id]);
      while (parent && !visited.has(parent.id)) {
        visited.add(parent.id);
        if (
          metric === "power" ? parent.power : parent.energy || parent.statistic
        )
          return false;
        parent = byId.get(parent.parent_id);
      }
      return true;
    };
    const sum = (values) =>
        values.some((v) => v == null)
          ? null
          : values.reduce((a, b) => a + Number(b), 0),
      homeW = e.home_power_live ?? e.values.home_power,
      homeKwh = t.home_energy,
      trackedW = sum(
        items
          .filter(
            (c) => c.counted_power ?? (Boolean(c.power) && counted(c, "power")),
          )
          .map((c) => c.power_w),
      ),
      trackedKwh = sum(
        items
          .filter(
            (c) =>
              c.counted_energy ??
              (Boolean(c.energy || c.statistic) && counted(c, "energy")),
          )
          .map((c) => c.period_kwh).filter(v => v != null),
      ),
      untrackedW =
        homeW == null || trackedW == null ? null : Number(homeW) - trackedW,
      untrackedKwh =
        homeKwh == null || trackedKwh == null
          ? null
          : Number(homeKwh) - trackedKwh;
    const window = e.power_windows?.[String(this.averageSeconds)],
      meanHome = window?.home_power_w ?? homeW,
      meanTracked = window?.tracked_power_w ?? trackedW,
      meanUntracked = window?.untracked_power_w ?? untrackedW;
    for (const item of items) item.average_w = window?.consumers?.[item.id] ?? item.power_w;
    const untracked = {id: "__untracked__", name: "Nieśledzone zużycie",
      power_w: untrackedW, average_w: meanUntracked, period_kwh: untrackedKwh};
    byId.set(untracked.id, untracked);
    if (!children.has(null)) children.set(null, []);
    children.get(null).push(untracked);
    const orderKey = `${this.data.revision}:${this.sortMode}:${this.sortDirection}:${this.averageSeconds}:${Math.floor(Date.now() / (Math.max(5, this.averageSeconds) * 1000))}:${items.map(c => c.id).join(",")}`;
    if (this._orderKey !== orderKey) {
      this._orderKey = orderKey;
      for (const [parent, group] of children) {
        const field = this.sortMode === "average" ? "average_w" : this.sortMode === "energy" ? "period_kwh" : "power_w";
        const sign = this.sortDirection === "asc" ? 1 : -1;
        this._orders.set(parent, [...group].sort((a, b) => {
          if (this.sortMode === "name") return sign * a.name.localeCompare(b.name, "pl");
          if (a[field] == null || b[field] == null)
            return (a[field] == null) - (b[field] == null) || a.name.localeCompare(b.name, "pl");
          return sign * (Number(a[field]) - Number(b[field])) || a.name.localeCompare(b.name, "pl");
        }).map(c => c.id));
      }
    }
    const values = (power, kwh, mean) =>
      `<span class="device-values"><strong role="cell">${fmt(power)} W</strong><small role="cell" class="device-average" title="Średnia ważona czasem z ${this.averageSeconds} s">${fmt(mean)} W</small><small role="cell">${precise(kwh)} kWh</small></span>`;
    const toolbar = `<label class="average-options">Średnia<select data-average aria-label="Okno średniej">${[1,5,10,15].map(n => `<option value="${n}" ${this.averageSeconds === n ? "selected" : ""}>${n} s</option>`).join("")}</select></label>`;
    const headers = `<div class="device-header" role="row">${[["name","Nazwa"],["power","Moc"],["average","Średnia"],["energy","Energia"]].map(([key,label]) => `<div role="columnheader" aria-sort="${this.sortMode === key ? this.sortDirection === "asc" ? "ascending" : "descending" : "none"}"><button data-sort="${key}" aria-pressed="${this.sortMode === key}">${label}${this.sortMode === key ? this.sortDirection === "asc" ? " ▴" : " ▾" : ""}</button></div>`).join("")}</div>`;
    const rows = (parent, depth = 0, visited = new Set()) =>
      (children.get(parent) || [])
        .sort((a, b) => (this._orders.get(parent)?.indexOf(a.id) ?? 0) - (this._orders.get(parent)?.indexOf(b.id) ?? 0))
        .filter((c) => !visited.has(c.id))
        .map((c) => {
          const seen = new Set(visited);
          seen.add(c.id);
          const nested = children.get(c.id)?.length,
            open = this._expanded.has(c.id);
          return `<div class="device ${c.id === "__untracked__" ? "untracked" : ""} ${nested ? "device-folder" : ""}" style="--depth:${depth}"><div class="device-line"><div class="device-content" role="row" data-consumer-id="${esc(c.id)}"><div class="device-name-cell" role="cell">${depth ? '<span class="tree-stem">└</span>' : ""}<button class="device-name" title="${esc(c.name)}">${esc(c.name)}</button></div>${values(c.power_w, c.period_kwh, c.average_w)}</div></div><div class="bar"><i style="width:${c.power_w != null && homeW > 0 ? Math.max(0, Math.min(100, (100 * Number(c.power_w)) / Number(homeW))) : 0}%"></i></div></div>${nested ? rows(c.id, depth + 1, seen) : ""}`;
        })
        .join("");
    this.frame(
      `<style>${periodCSS}.average-options{display:flex;align-items:center;justify-content:flex-end;gap:8px;font-size:12px;color:var(--secondary-text-color);margin:8px 0}.average-options select{width:auto;min-width:70px;padding:5px 8px;border-radius:8px}.consumer-total{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}.consumer-total>div{background:var(--secondary-background-color,#f3f6f7);padding:13px;border-radius:13px}.consumer-total small{display:block;font-size:11px;color:var(--secondary-text-color)}.consumer-total strong{display:block;font-size:clamp(19px,5cqw,27px);margin-top:4px}.consumer-summary{display:flex;justify-content:space-between;gap:10px;font-size:11px;color:var(--secondary-text-color);padding:5px 0 12px}.device-header,.device-content{display:grid;grid-template-columns:minmax(0,1.35fr) repeat(3,minmax(0,1fr));align-items:center;gap:5px;width:100%;min-width:0}.device-header{padding:9px 0;background:var(--secondary-background-color,#f3f6f7);border-radius:8px;font-size:11px}.device-header>div{text-align:right;min-width:0}.device-header>div:first-child{text-align:left}.device-header button{font-size:11px;padding:3px;color:var(--secondary-text-color);white-space:nowrap}.device-header [aria-sort=ascending] button,.device-header [aria-sort=descending] button{color:var(--primary-color);font-weight:700}.device{padding:11px 0 9px;border-top:1px solid var(--divider-color,#e7edef)}.device-name-cell{display:flex;align-items:center;min-width:0;padding-left:calc(var(--depth,0)*10px)}.folder-button,.tree-stem{flex:0 0 15px;padding:0;text-align:center;color:var(--pge-teal);font-size:13px}.device-name{font-size:12px;min-width:0;padding:0;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.untracked .device-name{white-space:normal;line-height:1.2}.device-values{display:contents}.device-values>*{text-align:right;white-space:nowrap;font-size:11px}.device-values strong{font-size:12px}.device-average{color:var(--pge-teal)}.device-values small:last-child{color:var(--secondary-text-color)}.bar{height:3px;margin-top:7px;background:var(--secondary-background-color,#edf2f3);border-radius:5px;overflow:hidden}.bar i{display:block;height:100%;background:var(--pge-teal)}</style><ha-card><div class="head"><h2>${esc(this.config.title || "Odbiorcy w domu")}</h2><span class="chip">Moc na żywo</span></div>${this.periodHTML()}<div class="consumer-total"><div><small>Cały dom · teraz</small><strong>${fmt(homeW)} W</strong><small>⌀ ${fmt(meanHome)} W · ${this.averageSeconds} s</small></div><div><small>Cały dom · okres</small><strong>${precise(homeKwh)} kWh</strong></div></div><div class="consumer-summary"><span>Śledzone</span><span>${fmt(trackedW)} W · ⌀ ${fmt(meanTracked)} W · ${precise(trackedKwh)} kWh</span></div>${toolbar}<div class="devices" role="table" aria-label="Odbiorcy w domu">${headers}${rows(null) || '<div class="empty">Dodaj odbiorców w panelu Energia.</div>'}</div>${(untrackedW != null && untrackedW < -0.05) || (untrackedKwh != null && untrackedKwh < -0.05) ? '<div class="warn">Suma śledzonych przekracza bilans domu. Sprawdź powiązania i punkty pomiarowe.</div>' : ""}${this._periodError ? `<div class="warn">${esc(this._periodError)}</div>` : ""}</ha-card>`,
    );
    this.bindPeriod();
    for (const button of this.shadowRoot.querySelectorAll("[data-sort]"))
      button.onclick = () => {
        if (this.sortMode === button.dataset.sort)
          this.sortDirection = this.sortDirection === "asc" ? "desc" : "asc";
        else { this.sortMode = button.dataset.sort; this.sortDirection = this.sortMode === "name" ? "asc" : "desc"; }
        this._orderKey = null; this.render();
      };
    this.shadowRoot.querySelector("[data-average]").onchange = event => {
      this.averageSeconds = Number(event.target.value); this._orderKey = null; this.render();
    };
    for (const button of this.shadowRoot.querySelectorAll("[data-folder]"))
      button.onclick = event => {
        event.stopPropagation();
        const id = button.dataset.folder;
        this._expanded.has(id)
          ? this._expanded.delete(id)
          : this._expanded.add(id);
        this.render();
      };
    for (const button of this.shadowRoot.querySelectorAll("[data-consumer-id]"))
      button.onclick = () => {
        const c = byId.get(button.dataset.consumerId),
          entity = c?.id === "__untracked__" ? this.data.entities?.untracked_power : c?.power || c?.energy;
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
    if (this._key !== `${this.data.entry_id}:${this.data.revision}:${this.data.hourly_revision || 0}`) {
      this._key = `${this.data.entry_id}:${this.data.revision}:${this.data.hourly_revision || 0}`;
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
    const rows = [...data.rows].sort((a, b) => a.day.localeCompare(b.day));
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
    )}</div><div class="daily-table"><table><thead><tr><th>Dzień</th><th>Pobrano</th><th>Oddano</th><th>Magazyn</th><th>Netto</th></tr></thead><tbody>${[...rows].reverse().map((r) => `<tr><td>${esc(day(r.day))}${r.partial ? " ·" : ""}</td><td class="minus">${fmt(r.import_kwh)}</td><td class="plus">${fmt(r.credited_kwh)}</td><td class="balance">${fmt(r.balance_kwh)}</td><td>${fmt(r.net_kwh)}</td></tr>`).join("")}</tbody></table></div>`;
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
  grid_import_energy: ["Energia pobrana z sieci", "kWh"],
  grid_export_energy: ["Energia oddana do sieci", "kWh"],
  grid_power: ["Moc sieci +/−", "W"],
  battery_power: ["Moc akumulatora +/−", "W"],
  pv_power: ["Moc PV · W/kW · Teraz", "W"],
  home_power: ["Własna encja mocy domu (opcjonalnie)", "W"],
  grid_import_power: ["Moc pobierana z sieci", "W"],
  grid_export_power: ["Moc oddawana do sieci", "W"],
  battery_charge_power: ["Moc ładowania", "W"],
  battery_discharge_power: ["Moc rozładowania", "W"],
  battery_soc: ["Poziom naładowania", "%"],
  battery_stored: ["Własna encja zapasu kWh (opcjonalnie)", "kWh"],
  pv_energy: ["Liczniki PV · kWh · Dzisiaj", "kWh"],
  home_energy: ["Własny licznik domu (opcjonalnie)", "kWh"],
  battery_charge_energy: ["Ładowanie — licznik", "kWh"],
  battery_discharge_energy: ["Rozładowanie — licznik", "kWh"],
};
class SettingsCard extends PGEBase {
  render() {
    if (this.shadowRoot.querySelector("dialog[open]")) return;
    const admin = this._hass?.user?.is_admin;
    const identity = `${this.data.entry_id}:${Boolean(admin)}:${this.data.version}`;
    if (
      this._settingsIdentity === identity &&
      this.shadowRoot.querySelector("ha-card")
    )
      return;
    this._settingsIdentity = identity;
    this.frame(
      `<style>dialog{color:var(--primary-text-color);background:var(--card-background-color,#fff);border:0;border-radius:20px;width:min(940px,96vw);max-height:90dvh;padding:0;box-shadow:0 20px 80px #0004}dialog::backdrop{background:#14283280;backdrop-filter:blur(3px)}.dialog-head{position:sticky;top:0;background:var(--card-background-color,#fff);z-index:2;padding:16px 20px;border-bottom:1px solid var(--divider-color,#dbe5e9);display:flex;justify-content:space-between;align-items:center}.tabs{display:flex;gap:6px;padding:12px 16px}.tabs .active{color:var(--primary-color,#3287bd);background:var(--secondary-background-color,#edf5f6)}.source-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.source-grid label{display:flex;flex-direction:column;gap:6px;font-size:12px}.source-section{margin:0 0 26px;padding-bottom:22px;border-bottom:1px solid var(--divider-color,#e7edef)}.source-field{min-width:0;display:grid;gap:6px;align-content:start}.source-field>label,.mode-label{font-size:12px;display:grid;gap:7px}.source-field select{width:100%;font-size:12px}.selected-source{display:flex;align-items:center;justify-content:space-between;gap:8px;background:var(--secondary-background-color,#f4f7f8);padding:9px;border-radius:9px;min-width:0}.selected-source span{min-width:0}.selected-source b{display:block;font-size:12px;overflow-wrap:anywhere}.selected-source small{display:block;font-size:10px;color:var(--secondary-text-color);overflow-wrap:anywhere}.source-missing{box-shadow:inset 3px 0 #bd6639}.source-missing small{color:#bd6639}.pv-report-row{margin-top:10px;padding-top:10px;border-top:1px solid var(--divider-color,#dbe3e7);overflow-wrap:anywhere}.pv-report-row div{margin-top:4px}.pv-report-row small,.source-origin{font-size:10px;color:var(--secondary-text-color)}.source-count{display:inline;font-size:11px;color:var(--secondary-text-color)}.section-note{margin:8px 0 14px}.source-notice{padding:10px 12px;border-radius:10px;background:var(--secondary-background-color,#f4f7f8);font-size:12px;line-height:1.5;margin-bottom:14px}.import-box{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.dashboard-box{border-top:1px solid var(--divider-color,#e7edef);padding-top:12px;margin-top:12px}.dashboard-box a{color:var(--primary-color);font-weight:600}.source-section h3{margin-bottom:12px}.consumer-config{display:grid;grid-template-columns:1fr 1.1fr 1.1fr 1fr auto;gap:8px;margin:10px 0}.consumer-config input,.consumer-config select{width:100%;font-size:12px}.footer{display:flex;align-items:center;justify-content:space-between;margin-top:20px}#source-status{font-size:12px;margin-top:10px}@media(max-width:600px){.consumer-config{grid-template-columns:1fr 1fr}.source-grid{grid-template-columns:1fr}dialog{width:96vw;max-height:94dvh}}</style><ha-card><div class="head" style="margin-bottom:8px"><h2>${esc(this.config.title || "Rozliczenia i ustawienia")}</h2><ha-icon icon="mdi:tune-variant"></ha-icon></div><div class="row">${admin ? '<button id="open-sources" class="primary">Źródła energii</button><button id="open-invoices">Faktury</button><button id="open-plan">Plan i partie</button>' : '<span class="sub">Ustawienia są dostępne dla administratora.</span>'}</div>${admin ? '<div class="dashboard-box"><button id="create-dashboard">▦ Utwórz dashboard z osobnych kart</button><div id="dashboard-status" class="sub" role="status"></div></div>' : ""}</ha-card><dialog><div class="dialog-head"><h2>Magazyn PGE</h2><button id="close-dialog" aria-label="Zamknij">✕</button></div><div class="tabs"><button data-tab="sources">Źródła energii</button><button data-tab="invoices">Faktury</button><button data-tab="plan">Plan i partie</button></div><div id="settings-panel"></div><div class="sub" style="padding:12px 20px;text-align:right">Integracja ${esc(this.data.version || "—")} · Karta ${VERSION}</div></dialog>`,
    );
    if (admin)
      for (const tab of ["sources", "invoices", "plan"])
        this.shadowRoot.getElementById(`open-${tab}`).onclick = () =>
          this.open(tab);
    if (admin)
      this.shadowRoot.getElementById("create-dashboard").onclick = () =>
        this.createDashboard();
    this.shadowRoot.getElementById("close-dialog").onclick = () =>
      this.shadowRoot.querySelector("dialog").close();
    for (const b of this.shadowRoot.querySelectorAll("[data-tab]"))
      b.onclick = () => this.tab(b.dataset.tab);
  }
  async createDashboard() {
    const button = this.shadowRoot.getElementById("create-dashboard"),
      status = this.shadowRoot.getElementById("dashboard-status");
    button.disabled = true;
    try {
      const result = await this.call("create_dashboard");
      if (!/^\/pge-energia-[a-z0-9-]+\/magazyn$/.test(result.url))
        throw new Error("Nieprawidłowy adres dashboardu.");
      status.innerHTML = `${result.created ? "Utworzono osobne karty." : "Dashboard jest już gotowy."} <a id="open-dashboard" href="${esc(result.url)}">Otwórz dashboard →</a>`;
    } catch (error) {
      status.textContent = error.message || String(error);
      status.className = "error";
    } finally {
      button.disabled = false;
    }
  }
  open(tab = "sources") {
    if (!this._hass.user?.is_admin) return;
    this._energyRevision = this.data.revision;
    this._gridMode = null;
    this._batteryMode = null;
    this._capacityMode = null;
    this._importWarnings = null;
    this._importReport = this.data.energy?.import_report || [];
    this._sourceDraft = JSON.parse(
      JSON.stringify(
        this.data.energy?.config || { sources: {}, consumers: [] },
      ),
    );
    this.shadowRoot.getElementById("settings-panel").replaceChildren();
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
    const selectedIds = Array.isArray(selected)
      ? selected
      : selected
        ? [selected]
        : [];
    for (const id of selectedIds) if (!ids.includes(id)) ids.push(id);
    ids.sort((a, b) =>
      (this._hass.states[a]?.attributes?.friendly_name || a).localeCompare(
        this._hass.states[b]?.attributes?.friendly_name || b,
        "pl",
      ),
    );
    return `<option value="">Nie podłączono</option>${ids.map((id) => `<option value="${esc(id)}" ${selectedIds.includes(id) ? "selected" : ""}>${esc(this._hass.states[id]?.attributes?.friendly_name || id)} (${esc(id)})</option>`).join("")}`;
  }
  readSources() {
    const root = this.shadowRoot,
      draft = this._sourceDraft || {},
      list = (v) => (Array.isArray(v) ? v : v ? [v] : []);
    const sources = Object.fromEntries(
      [...root.querySelectorAll("[data-source]")]
        .map((input) => {
          const ids = input.dataset.multi
            ? [
                ...list(draft.sources?.[input.dataset.source]),
                ...list(input.value),
              ]
            : list(input.value);
          const unique = [...new Set(ids.filter(Boolean))];
          return [
            input.dataset.source,
            unique.length > 1 ? unique : unique[0] || null,
          ];
        })
        .filter(([, value]) => value),
    );
    const statistics = { ...(draft.statistics || {}) };
    for (const key of Object.keys(statistics))
      if (
        JSON.stringify(list(sources[key]).sort()) !==
        JSON.stringify(list(draft.sources?.[key]).sort())
      ) {
        if (root.querySelector(`[data-source="${key}"]`)?.dataset.multi) {
          const ids = [
            ...statistics[key].filter((id) => !id.startsWith("sensor.")),
            ...list(sources[key]),
          ];
          if (ids.length) statistics[key] = [...new Set(ids)];
          else delete statistics[key];
        } else delete statistics[key];
      }
    const directions = {
      ...draft.directions,
      ...Object.fromEntries(
        [...root.querySelectorAll("[data-direction]")].map((input) => [
          input.dataset.direction,
          input.value,
        ]),
      ),
    };
    return {
      ...draft,
      sources,
      statistics,
      directions,
      battery_capacity_kwh:
        root.querySelector("[data-capacity]")?.value || null,
      battery_capacity_ah:
        root.querySelector("[data-capacity-ah]")?.value || null,
      battery_voltage: root.querySelector("[data-voltage]")?.value || null,
      flow_clock_source: list(sources.pv_power).includes(root.querySelector("[data-flow-clock]")?.value) ? root.querySelector("[data-flow-clock]").value : null,
      flow_mode: root.querySelector("[data-flow-mode]")?.value || "aligned",
      show_hour: root.querySelector("[data-show-hour]")?.checked ?? true,
      pv_order: [...root.querySelectorAll("[data-pv-order]")].map(n=>n.dataset.pvOrder),
      battery_forecast: {
        enabled: root.querySelector("[data-eta-enabled]")?.checked ?? true,
        learn: root.querySelector("[data-eta-learn]")?.checked ?? false,
        average_minutes: Number(root.querySelector("[data-eta-average]")?.value || 5),
        forecast_hours: Number(root.querySelector("[data-forecast-hours]")?.value || 6),
        ...Object.fromEntries([...root.querySelectorAll("[data-battery-option]")].map(n=>[n.dataset.batteryOption,n.value||null]))
      },
      consumers: [...root.querySelectorAll(".consumer-config")]
        .map((row, index) => {
          const old = draft.consumers?.[index] || {},
            value = row.querySelector("[data-energy]").value,
            item = {
              ...(old.id ? { id: old.id } : {}),
              parent_id: row.querySelector("[data-parent]")?.value || null,
              name: row.querySelector("input").value,
              power: row.querySelector("[data-power]").value,
              energy: value,
            };
          if (old.statistic && value === (old.energy || ""))
            item.statistic = old.statistic;
          return item;
        })
        .filter((c) => c.name || c.power || c.energy || c.statistic),
    };
  }
  async importPanel() {
    const status = this.shadowRoot.getElementById("source-status");
    try {
      const result = await this.call("energy_defaults");
      this._sourceDraft = result.config;
      this._importReport = result.report || [];
      this._importWarnings = result.warnings || [];
      this._energyRevision = this.data.revision;
      this._gridMode = null;
      this._batteryMode = null;
      this.sourcesHTML();
      this.shadowRoot.getElementById("source-status").textContent =
        `Wczytano źródła. ${this._importWarnings.join(" ")} Kliknij „Zapisz źródła”, aby zastosować.`;
    } catch (error) {
      status.textContent = error.message || String(error);
      status.className = "error";
    }
  }
  sourcesHTML() {
    const config = this._sourceDraft,
      list = (v) => (Array.isArray(v) ? v : v ? [v] : []);
    const sourceName = (id) =>
      this._hass.states[id]?.attributes?.friendly_name || id;
    const report = this._importReport || this.data.energy?.import_report || [];
    const origin = (key, id) => {
      for (const item of report)
        for (const detail of [...item.energy, ...item.power, ...item.soc])
          if (detail.id === id && detail.role === key)
            return {
              label: `Źródło: Energia → ${item.type === "solar" ? "Panele słoneczne" : item.type === "battery" ? "Akumulator" : "Sieć"} → ${item.name} → ${key.endsWith("power") ? "Moc" : key === "battery_soc" ? "SOC" : "Energia"}`,
              path: detail.origin?.path || "",
            };
      return { label: "Wybrane ręcznie", path: "" };
    };
    const pvReport = report.filter((item) => item.type === "solar");
    const pvReportHTML = pvReport.length
      ? `<div id="pv-import-report" class="source-notice"><b>Instalacje PV w Energii: ${pvReport.length}</b><div class="sub">Liczniki kWh i pomiary W są osobnymi polami. Nie dobieramy sensorów mocy po nazwie licznika.</div>${pvReport.map((item) => `<div class="pv-report-row"><b>${esc(item.name)}</b><div>kWh: ${item.energy.map((detail) => `<span title="${esc(detail.origin?.path)}">${esc(detail.name)} <small>(${esc(detail.id)})</small></span>`).join(" + ") || "brak"}</div><div>W: ${item.power.map((detail) => `<span title="${esc(detail.origin?.path)}">${esc(detail.name)} <small>(${esc(detail.id)})</small></span>`).join(" + ") || "Brak pomiaru w Energii → 0 W"}</div></div>`).join("")}</div>`
      : "";
    const field = (key) => {
      const [title, unit] = sourceRoles[key],
        value = config.sources[key],
        ids = list(value),
        multi =
          key.startsWith("pv_") ||
          key === "grid_power" ||
          key === "battery_power" ||
          Array.isArray(value);
      const external = (config.statistics?.[key] || []).filter(
        (id) => !id.startsWith("sensor."),
      );
      const selected = multi
        ? [...ids, ...external]
            .map((id) => {
              const state = this._hass.states[id],
                isExternal = !id.startsWith("sensor."),
                missing = !isExternal && !state,
                unavailable =
                  state && ["unavailable", "unknown"].includes(state.state);
              const provenance = origin(key, id);
              return `<div class="selected-source ${missing || unavailable ? "source-missing" : ""}"><span><b>${esc(sourceName(id))}</b><small>${esc(id)}${missing ? " · BRAK ENCJI" : unavailable ? " · niedostępna" : isExternal ? " · statystyka zewnętrzna" : ""}${unit === "W" && (missing || unavailable) ? " → 0 W" : ""}</small><small class="source-origin" title="${esc(provenance.path)}">${esc(provenance.label)}</small></span><button type="button" data-remove-source="${key}" data-id="${esc(id)}" aria-label="Usuń ${esc(id)}">✕</button></div>`;
            })
            .join("")
        : "";
      const placeholder =
        key === "battery_stored"
          ? "Z SOC i pojemności"
          : key.startsWith("home_")
            ? "Oblicz z bilansu"
            : multi
              ? "＋ Dodaj źródło…"
              : config.statistics?.[key]
                ? "Statystyki panelu Energia"
                : "Nie podłączono";
      const options = this.options(unit, multi ? null : value).replace(
        "Nie podłączono",
        placeholder,
      );
      return `<div class="source-field"><label>${title}${multi ? ` <span class="source-count">${ids.length + external.length}</span>` : ""}</label>${selected}<select data-source="${key}" ${multi ? 'data-multi="true"' : ""} aria-label="${esc(title)}">${options}</select>${config.statistics?.[key] ? '<small class="sub">kWh ze statystyk panelu Energia</small>' : ""}</div>`;
    };
    const gridMode =
        this._gridMode ||
        (config.sources.grid_import_power || config.sources.grid_export_power
          ? "split"
          : "signed"),
      batteryMode =
        this._batteryMode ||
        (config.sources.battery_charge_power ||
        config.sources.battery_discharge_power
          ? "split"
          : "signed");
    const mode = (kind, current) =>
      `<label class="mode-label">Pomiar mocy<select data-power-mode="${kind}"><option value="signed" ${current === "signed" ? "selected" : ""}>Jeden sensor +/− (lub suma faz)</option><option value="split" ${current === "split" ? "selected" : ""}>Dwa osobne kierunki</option></select></label>`;
    const direction = (kind) =>
      `<label class="mode-label">Wartość dodatnia oznacza<select data-direction="${kind}">${(kind ===
      "grid"
        ? [
            ["import", "Pobór z sieci"],
            ["export", "Oddawanie do sieci"],
          ]
        : [
            ["discharge", "Rozładowanie akumulatora"],
            ["charge", "Ładowanie akumulatora"],
          ]
      )
        .map(
          ([value, label]) =>
            `<option value="${value}" ${(config.directions?.[kind] || (kind === "grid" ? "import" : "charge")) === value ? "selected" : ""}>${label}</option>`,
        )
        .join("")}</select></label>`;
    const capacityMode =
      this._capacityMode ||
      (config.battery_capacity_ah && !config.battery_capacity_kwh
        ? "ah"
        : "kwh");
    const orderedPV = [...list(config.sources.pv_power)].reverse().sort((a,b) => {const rank = id => (config.pv_order || []).indexOf(id)<0 ? 999 : config.pv_order.indexOf(id);return rank(a)-rank(b);});
    const clockField = `<div class="form-grid"><label>Odświeżanie diagramu<select data-flow-mode><option value="aligned" ${config.flow_mode !== "latest" ? "selected" : ""}>Wyrównane · co 3 s, opóźnienie 12 s</option><option value="latest" ${config.flow_mode === "latest" ? "selected" : ""}>Najnowsze odczyty · co 3 s</option></select></label><label><input type="checkbox" data-show-hour ${config.show_hour !== false ? "checked" : ""}> Pokaż bieżącą godzinę między Siecią a Domem</label></div><div class="sub">Wyrównanie interpoluje raporty PV. Nie zmienia liczników kWh. Pierwsze 27 s służy zebraniu danych.</div><div><b>Kolejność instalacji po lewej</b>${orderedPV.map(id=>`<div data-pv-order="${esc(id)}"><span>${esc(sourceName(id))}</span><button data-pv-up="${esc(id)}" aria-label="Przesuń wyżej">↑</button><button data-pv-down="${esc(id)}" aria-label="Przesuń niżej">↓</button></div>`).join("")}</div>`;
    const batteryOpt = config.battery_forecast || {};
    const batterySelect = (key,label,units) => `<label>${label}<select data-battery-option="${key}"><option value="">Nie podłączono</option>${Object.entries(this._hass.states).filter(([id,state])=>/^(sensor|number)\./.test(id) && units.includes(state.attributes?.unit_of_measurement) && !Object.values(this.data.entities||{}).includes(id)).map(([id,state])=>`<option value="${esc(id)}" ${batteryOpt[key]===id ? "selected" : ""}>${esc(state.attributes.friendly_name||id)} (${esc(id)})</option>`).join("")}</select></label>`;
    const batteryTimeFields = `<h3>Czas ładowania i rozładowania</h3><label><input data-eta-enabled type="checkbox" ${batteryOpt.enabled !== false ? "checked" : ""}> Pokazuj estymację czasu</label><div class="form-grid"><label>Średnia mocy<select data-eta-average>${[1,5,15].map(n=>`<option value="${n}" ${(batteryOpt.average_minutes||5)===n ? "selected" : ""}>${n} min</option>`).join("")}</select></label>${batterySelect("min_soc_entity","Aktualne minimum SOC",["%"])}${batterySelect("charge_limit_entity","Limit mocy ładowania (opcjonalnie)",["W","kW"])}${batterySelect("bms_current_entity","Dopuszczalny prąd ładowania BMS (opcjonalnie)",["A"])}${batterySelect("voltage_entity","Napięcie baterii dla limitu BMS",["V"])}</div><label><input data-eta-learn type="checkbox" ${batteryOpt.learn ? "checked" : ""}> Ucz profil ograniczenia ładowania</label><div class="sub">Uczenie wymaga prądu dopuszczanego przez BMS i napięcia. Brak pełnego profilu nie blokuje estymacji z obecnej mocy. Moc poniżej 25 W nie daje czasu.</div><h3>Opcjonalny scenariusz PV</h3><div class="form-grid">${batterySelect("pv_forecast_entity","Prognozowana produkcja w horyzoncie (energia)",["kWh","Wh"])}${batterySelect("home_forecast_entity","Prognozowane zużycie domu w tym samym horyzoncie",["kWh","Wh"])}<label>Wspólny horyzont · godziny<input data-forecast-hours type="number" min="1" max="24" value="${esc(batteryOpt.forecast_hours||6)}"></label></div><div class="sub">Wybierz dwie zgodne prognozy energii pozostałej w tym samym horyzoncie. Nie sumujemy automatycznie prognoz kilku instalacji ani nie zgadujemy formatu atrybutów.</div>`;
    const capacityFields = `<label class="mode-label">Jednostka pojemności<select data-capacity-mode><option value="kwh" ${capacityMode === "kwh" ? "selected" : ""}>kWh</option><option value="ah" ${capacityMode === "ah" ? "selected" : ""}>Ah + napięcie nominalne</option></select></label>${capacityMode === "kwh" ? `<label class="mode-label">Pojemność odpowiadająca 0–100% SOC · kWh<input data-capacity type="number" min="0" step="any" placeholder="opcjonalnie" value="${esc(config.battery_capacity_kwh)}"></label>` : `<label class="mode-label">Łączna pojemność zestawu · Ah<input data-capacity-ah type="number" min="0" step="any" placeholder="np. 99" value="${esc(config.battery_capacity_ah)}"></label><label class="mode-label">Napięcie nominalne zestawu · V<input data-voltage type="number" min="0" step="any" placeholder="z dokumentacji baterii" value="${esc(config.battery_voltage)}"></label>`}`;
    const warnings =
      this._importWarnings || this.data.energy?.import_warnings || [];
    this.shadowRoot.getElementById("settings-panel").innerHTML =
      `<div style="padding:8px 20px 24px"><div class="source-section import-box"><button id="import-energy-panel" class="primary">Wczytaj z panelu Energia</button><span class="sub">Kopiujemy źródła. Każde można zmienić poniżej.</span></div>${warnings.length ? `<div class="source-notice">${warnings.map((w) => `<div>${esc(w)}</div>`).join("")}</div>` : ""}<div class="source-section"><h3>Panele słoneczne</h3>${pvReportHTML}${clockField}<div class="sub section-note">Brak odczytu mocy danego źródła oznacza 0 W. Pozostałe źródła są nadal sumowane. Każda instalacja jest widoczna osobno. Wybierz licznik łączny albo jego składowe — nie oba naraz.</div><div class="source-grid">${["pv_energy", "pv_power"].map(field).join("")}</div></div><div class="source-section"><h3>Dom</h3><div class="source-notice">Liczymy automatycznie: PV + sieć + rozładowanie − eksport − ładowanie. Własna encja jest opcjonalna. Brakująca moc wnosi 0 W.</div><div class="source-grid">${["home_power", "home_energy"].map(field).join("")}</div></div><div class="source-section"><h3>Sieć · energia i moc</h3><div class="sub section-note">kWh = ile przepłynęło. W/kW = ile płynie teraz. Dla Victrona wybierz liczniki „energymeter_consumption” i „energymeter_feed_in”; moc z punktu przyłączenia do sieci, łącznie dla faz. Liczniki faktur PGE pozostają wybraną wcześniej parą.</div><div class="source-grid">${["grid_import_energy", "grid_export_energy"].map(field).join("")}</div><div class="source-grid" style="margin-top:16px">${mode("grid", gridMode)}${gridMode === "signed" ? direction("grid") : ""}</div><div class="source-grid" style="margin-top:12px">${(gridMode === "signed" ? ["grid_power"] : ["grid_import_power", "grid_export_power"]).map(field).join("")}</div><div class="sub section-note">${gridMode === "signed" ? "Z jednego pomiaru wyliczamy pobór = max(moc, 0), oddawanie = max(−moc, 0), po uwzględnieniu wybranego znaku. Osobnych sensorów kierunków nie potrzebujesz." : "Oba kierunki mierzone oddzielnie, wartości nieujemne. Nie wybieraj dodatkowo sensora +/−."}</div></div><div class="source-section"><h3>Lokalny akumulator</h3><div class="sub section-note">To fizyczna bateria w domu. Importujemy to, co zapisano w Energii. Brakująca moc jest liczona jako 0 W. Zapas baterii w kWh jest opcjonalny i nie jest potrzebny do obliczania mocy domu.</div><div class="source-grid">${["battery_soc", "battery_stored"].map(field).join("")}${capacityFields}${batteryTimeFields}</div><div id="battery-estimate" class="source-notice" role="status"></div><div class="sub section-note">Własna encja zapasu kWh jest opcjonalna — chodzi o sensor pokazujący aktualnie zgromadzoną energię, a nie licznik ładowania. Zostaw ją pustą i wybierz SOC. Pojemność wpisz w kWh albo wybierz Ah + napięcie nominalne. Samo 99 Ah nie wystarczy: kWh = Ah × V / 1000. Do procentów wystarczy sam SOC.</div><div class="source-grid">${mode("battery", batteryMode)}${batteryMode === "signed" ? direction("battery") : ""}</div><div class="source-grid" style="margin-top:12px">${(batteryMode === "signed" ? ["battery_power"] : ["battery_charge_power", "battery_discharge_power"]).map(field).join("")}</div><div class="sub section-note">Moc: chwilowe ładowanie lub rozładowanie w W/kW. Znak ustaw zgodnie z odczytem Victrona — sprawdź podczas ładowania.</div><div class="source-grid">${["battery_charge_energy", "battery_discharge_energy"].map(field).join("")}</div><div class="sub section-note">Liczniki kWh: łączna energia wtłoczona do baterii i z niej pobrana. W Energii służą do bilansu dnia; nie stosujemy tu opustu PGE.</div></div><div class="source-section"><h3>Odbiorcy w domu</h3><div class="sub">Pokazywani na osobnej karcie „Odbiorcy w domu”. Nie dodajemy ich ponownie do bilansu domu.</div>${config.consumers
        .map(
          (c, i) =>
            `<div class="consumer-config"><input aria-label="Nazwa odbiorcy" placeholder="np. Pompa ciepła" value="${esc(c.name)}"><select data-power aria-label="Moc odbiorcy">${this.options("W", c.power)}</select><select data-energy aria-label="Licznik odbiorcy">${this.options("kWh", c.energy).replace("Nie podłączono", c.statistic ? "Statystyki Energii" : "Nie podłączono")}</select><select data-parent aria-label="Urządzenie nadrzędne"><option value="">Bez urządzenia nadrzędnego</option>${config.consumers
              .filter((p, j) => j !== i)
              .map((p) => {
                const id = p.id || p.statistic || p.energy || p.power;
                return `<option value="${esc(id)}" ${c.parent_id === id ? "selected" : ""}>${esc(p.name)}</option>`;
              })
              .join(
                "",
              )}</select><button data-remove="${i}" aria-label="Usuń odbiorcę">✕</button></div>`,
        )
        .join(
          "",
        )}<button id="add-consumer">＋ Dodaj odbiorcę</button></div><div class="footer"><button id="save-sources" class="primary">Zapisz źródła</button><span class="sub">Bez restartu HA</span></div><div id="source-status" role="status"></div></div>`;
    this.shadowRoot.getElementById("import-energy-panel").onclick = () =>
      this.importPanel();
    this.shadowRoot.getElementById("add-consumer").onclick = () => {
      this._sourceDraft = this.readSources();
      if (this._sourceDraft.consumers.length < 16)
        this._sourceDraft.consumers.push({ name: "", power: "", energy: "" });
      this.sourcesHTML();
    };
    for (const button of this.shadowRoot.querySelectorAll("[data-remove]"))
      button.onclick = () => {
        this._sourceDraft = this.readSources();
        const [removed] = this._sourceDraft.consumers.splice(
          Number(button.dataset.remove),
          1,
        );
        const id =
          removed.id || removed.statistic || removed.energy || removed.power;
        for (const c of this._sourceDraft.consumers)
          if (c.parent_id === id) c.parent_id = null;
        this.sourcesHTML();
      };
    for (const button of this.shadowRoot.querySelectorAll("[data-pv-up],[data-pv-down]")) button.onclick = () => {
      const row=button.closest("[data-pv-order]"), previous=row.previousElementSibling, next=row.nextElementSibling;
      if (button.dataset.pvUp && previous?.hasAttribute("data-pv-order")) row.parentNode.insertBefore(row,previous);
      if (button.dataset.pvDown && next?.hasAttribute("data-pv-order")) row.parentNode.insertBefore(next,row);
    };
    for (const input of this.shadowRoot.querySelectorAll(
      "[data-source][data-multi]",
    ))
      input.onchange = () => {
        this._sourceDraft = this.readSources();
        this.sourcesHTML();
      };
    for (const button of this.shadowRoot.querySelectorAll(
      "[data-remove-source]",
    ))
      button.onclick = () => {
        const key = button.dataset.removeSource,
          id = button.dataset.id;
        this._sourceDraft = this.readSources();
        const rest = list(this._sourceDraft.sources[key]).filter(
          (v) => v !== id,
        );
        if (rest.length)
          this._sourceDraft.sources[key] = rest.length === 1 ? rest[0] : rest;
        else delete this._sourceDraft.sources[key];
        if (this._sourceDraft.statistics?.[key]) {
          this._sourceDraft.statistics[key] = this._sourceDraft.statistics[
            key
          ].filter((v) => v !== id);
          if (!this._sourceDraft.statistics[key].length)
            delete this._sourceDraft.statistics[key];
        }
        this.sourcesHTML();
      };
    for (const input of this.shadowRoot.querySelectorAll("[data-power-mode]"))
      input.onchange = () => {
        const kind = input.dataset.powerMode;
        this._sourceDraft = this.readSources();
        this[kind === "grid" ? "_gridMode" : "_batteryMode"] = input.value;
        for (const role of kind === "grid"
          ? ["grid_power", "grid_import_power", "grid_export_power"]
          : [
              "battery_power",
              "battery_charge_power",
              "battery_discharge_power",
            ])
          delete this._sourceDraft.sources[role];
        this.sourcesHTML();
      };
    for (const input of this.shadowRoot.querySelectorAll(
      '[data-capacity],[data-capacity-ah],[data-voltage],[data-source="battery_soc"],[data-source="battery_stored"]',
    )) {
      input.addEventListener("input", () => this.updateBatteryPreview());
      input.addEventListener("change", () => this.updateBatteryPreview());
    }
    this.shadowRoot.querySelector("[data-capacity-mode]").onchange = (
      event,
    ) => {
      this._sourceDraft = this.readSources();
      this._capacityMode = event.target.value;
      this.sourcesHTML();
    };
    this.updateBatteryPreview();
    this.shadowRoot.getElementById("save-sources").onclick = () =>
      this.saveSources();
  }
  updateBatteryPreview() {
    const output = this.shadowRoot.getElementById("battery-estimate");
    if (!output) return;
    const config = this.readSources(),
      state = (id) => this._hass.states[id],
      number = (value) =>
        value != null &&
        String(value).trim() !== "" &&
        Number.isFinite(Number(value))
          ? Number(value)
          : null;
    const id = config.sources.battery_stored,
      own = id && state(id),
      scale = { Wh: 0.001, kWh: 1, MWh: 1000 }[
        own?.attributes?.unit_of_measurement
      ],
      ownValue = number(own?.state);
    const format = (value) =>
      new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2 }).format(
        value,
      );
    if (ownValue != null && ownValue >= 0 && scale) {
      output.textContent = `Zapas z wybranej encji: ${format(ownValue * scale)} kWh.`;
      return;
    }
    const socState = state(config.sources.battery_soc),
      soc =
        socState?.attributes?.unit_of_measurement === "%"
          ? number(socState.state)
          : null,
      explicit = number(config.battery_capacity_kwh),
      ah = number(config.battery_capacity_ah),
      voltage = number(config.battery_voltage),
      capacity =
        explicit || (ah > 0 && voltage > 0 ? (ah * voltage) / 1000 : null);
    if (soc != null && soc >= 0 && soc <= 100 && capacity > 0)
      output.textContent = `Zapas obliczony: ${format(soc)}% × ${format(capacity)} kWh = ${format((soc * capacity) / 100)} kWh.${!explicit && ah && voltage ? ` Pojemność: ${format(ah)} Ah × ${format(voltage)} V / 1000 = ${format(capacity)} kWh.` : ""}`;
    else if (ah > 0 && !voltage)
      output.textContent =
        "Podaj napięcie nominalne baterii w V. Samo Ah nie określa pojemności kWh.";
    else if (soc != null)
      output.textContent = `Poziom baterii: ${format(soc)}%. Możesz zostawić zapas kWh pusty albo podać pojemność użytkową.`;
    else
      output.textContent =
        "Zapas kWh jest opcjonalny. Pozostaw własną encję pustą; do obliczenia zapasu wybierz SOC (%) i wpisz pojemność użytkową baterii (kWh).";
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
    this.shadowRoot.innerHTML = `<style>:host{display:block;min-width:0;container-type:inline-size}.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:16px;max-width:1400px;margin:auto}.stack{display:grid;gap:16px;align-content:start;min-width:0}.stack>*{min-width:0}.tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.wide{grid-column:1/-1}@container(max-width:800px){.layout{grid-template-columns:minmax(0,1fr)}}@container(max-width:420px){.tiles{gap:6px}}</style><div class="layout"><div class="stack"><pge-energy-card data-module></pge-energy-card><pge-settings-card data-module></pge-settings-card><pge-opust-card data-module></pge-opust-card><pge-consumers-card data-module></pge-consumers-card></div><div class="stack"><div class="tiles">${["available_energy", "deficit", "period_balance"].map((key) => `<pge-balance-card data-module data-metric="${key}"></pge-balance-card>`).join("")}</div><pge-projection-card data-module></pge-projection-card></div><pge-history-card class="wide" data-module></pge-history-card></div>`;
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
    }${this.config.type === "custom:pge-energy-card" ? `<label><input type="checkbox" data-key="show_hour" ${this.config.show_hour !== false ? "checked" : ""}> Pokaż bieżącą godzinę</label>` : ""}`;
    for (const input of this.querySelectorAll("[data-key]"))
      input.onchange = () => {
        const config = { ...this.config, [input.dataset.key]: input.type === "checkbox" ? input.checked : input.value };
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
  ["pge-hour-card", HourCard],
  ["pge-opust-card", OpustCard],
  ["pge-consumers-card", ConsumersCard],
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
  ["pge-hour-card", "PGE · Bieżąca godzina", "Roboczy bilans: plus pobór, minus eksport"],
  ["pge-opust-card", "PGE · Potrącenie opustu", "Energia potrącona w wybranym okresie"],
  [
    "pge-energy-card",
    "PGE · Energia w domu",
    "Moc teraz i energia dzisiaj razem: PV, dom, sieć, akumulator i PGE",
  ],
  [
    "pge-consumers-card",
    "PGE · Odbiorcy w domu",
    "Osobna karta urządzeń, mocy i dzisiejszej energii",
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
