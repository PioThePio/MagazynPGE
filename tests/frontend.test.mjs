import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import { Window } from "happy-dom";
const dir = new URL(
  "../custom_components/pge_storage/frontend/",
  import.meta.url,
);
const script = readFileSync(
  new URL("pge-storage-card.js", dir),
  "utf8",
).replace(/^import .*;$/m, "");
const adminScript = readFileSync(new URL("pge-settings.js", dir), "utf8");
const tick = () => new Promise((r) => setImmediate(r));
const snapshot = () => ({
  entry_id: "test",
  revision: 3,
  loaded: true,
  sources: { import: "sensor.import", export: "sensor.export" },
  source_values: { import: "2443", export: "4630" },
  current: {
    available_energy: "2197.032",
    deficit: "0",
    period_balance: "33.032",
    carried_balance: "2164",
    start_day: "2026-09-30",
  },
  records: [
    {
      id: "invoice",
      day: "2026-09-30",
      invoice_balance: "2164",
      carried_balance: "2164",
      sample: {
        value: "1228.06",
        recorded_at: "2026-09-30T21:45:00Z",
        components: {
          import: { value: "2308.9", recorded_at: "2026-09-30T21:45:00Z" },
          export: { value: "4421.2", recorded_at: "2026-09-30T14:48:00Z" },
        },
      },
      note: "Faktura",
    },
  ],
  entities: {
    available_energy: "sensor.balance",
    pv_power: "sensor.alias_pv_power",
  },
  energy: {
    config: { sources: {}, consumers: [] },
    values: { pv_power: "2500", home_power: "1200", battery_soc: "78" },
    today: {
      pv_energy: "6.56",
      home_energy: "14.7",
      grid_import_energy: "8.24",
      grid_export_energy: "1.59",
    },
    consumers: [],
  },
  comparison: [],
  planning: {
    config: { anchor_id: null, lots: [], profile: [] },
    target_day: "2027-03-31",
    inventory: null,
    forecast: null,
  },
});
async function setup(tag = "pge-storage-card", admin = true) {
  const window = new Window();
  for (const code of [adminScript, script])
    runInNewContext(code, {
      window,
      HTMLElement: window.HTMLElement,
      customElements: window.customElements,
      CustomEvent: window.CustomEvent,
      Intl,
      Date,
      URL: window.URL,
      Blob: window.Blob,
      setTimeout,
      confirm: () => true,
    });
  const listeners = new Set(),
    calls = [];
  let subscriptions = 0,
    stopped = 0;
  const hass = {
    user: { is_admin: admin },
    states: {
      "sensor.pv": {
        state: "2500",
        attributes: { friendly_name: "Fotowoltaika", unit_of_measurement: "W" },
      },
      "sensor.pv_energy": {
        state: "1000",
        attributes: { unit_of_measurement: "kWh" },
      },
      "sensor.alias_pv_power": {
        state: "2500",
        attributes: { unit_of_measurement: "W" },
      },
    },
    connection: {
      subscribeMessage: async (fn, msg) => {
        subscriptions++;
        calls.push(msg);
        listeners.add(fn);
        fn(snapshot());
        return () => {
          listeners.delete(fn);
          stopped++;
        };
      },
    },
    callWS: async (cmd) => {
      calls.push(cmd);
      if (cmd.type === "pge_storage/months")
        return {
          rows: [
            {
              month: "2026-10",
              import_kwh: "10",
              credited_kwh: "18",
              net_kwh: "8",
              balance_kwh: "2172",
            },
          ],
        };
      if (cmd.type === "pge_storage/daily")
        return {
          rows: [
            {
              day: "2026-10-01",
              import_kwh: "5",
              credited_kwh: "8",
              net_kwh: "3",
              balance_kwh: "2167",
            },
            {
              day: "2026-10-02",
              import_kwh: null,
              credited_kwh: null,
              net_kwh: null,
              balance_kwh: null,
            },
          ],
        };
      return null;
    },
  };
  const card = window.document.createElement(tag);
  card.setConfig({ type: `custom:${tag}` });
  window.document.body.append(card);
  card.hass = hass;
  await tick();
  return {
    window,
    card,
    root: card.shadowRoot,
    calls,
    hass,
    emit: (data) => {
      for (const fn of listeners) fn(data);
    },
    subscriptions: () => subscriptions,
    stopped: () => stopped,
  };
}
test("dashboard is separate cards sharing one backend subscription", async () => {
  const { window, root, subscriptions, card, stopped } = await setup();
  assert.equal(root.querySelectorAll("pge-balance-card").length, 3);
  assert.equal(
    root.querySelectorAll(
      "pge-energy-card,pge-history-card,pge-projection-card,pge-settings-card",
    ).length,
    4,
  );
  assert.equal(root.querySelector("ha-card"), null);
  assert.equal(subscriptions(), 1);
  card.remove();
  await tick();
  assert.equal(stopped(), 1);
  await window.happyDOM.close();
});
test("balance tile rounds whole kWh and opens its reusable HA entity", async () => {
  const { window, card, root } = await setup("pge-balance-card");
  assert.match(root.textContent, /2197 kWh/);
  assert.doesNotMatch(root.textContent, /,0|,032/);
  let id;
  card.addEventListener("hass-more-info", (e) => (id = e.detail.entityId));
  root.getElementById("metric").click();
  assert.equal(id, "sensor.balance");
  await window.happyDOM.close();
});
test("energy diagram distinguishes daily energy, live power and missing values", async () => {
  const { window, root, card } = await setup("pge-energy-card");
  assert.match(root.querySelector(".node-pv").textContent, /7 kWh/);
  assert.match(root.querySelector(".node-grid").textContent, /8 kWh/);
  assert.match(root.querySelector(".node-pge").textContent, /2197 kWh/);
  root.querySelector('[data-mode="power"]').click();
  assert.match(root.querySelector(".node-pv").textContent, /2500 W/);
  assert.match(root.querySelector(".node-grid").textContent, /— W/);
  assert.equal(card.mode, "power");
  await window.happyDOM.close();
});
test("month settlement expands to compact days with balance before net and real gaps", async () => {
  const { window, root } = await setup("pge-history-card");
  root.querySelector('[data-month="2026-10"] button').click();
  await tick();
  const rows = root.querySelectorAll('[data-days="2026-10"] tbody tr');
  assert.equal(rows.length, 2);
  assert.equal(rows[0].children.length, 5);
  assert.equal(rows[0].children[1].textContent, "5");
  assert.equal(rows[0].children[2].textContent, "8");
  assert.equal(rows[0].children[3].textContent, "2167");
  assert.equal(rows[0].children[4].textContent, "3");
  assert.match(rows[1].textContent, /—/);
  assert.equal(root.querySelectorAll("svg.chart").length, 2);
  assert.doesNotMatch(root.textContent, /Czasy|niepokryty|przed opustem/);
  await window.happyDOM.close();
});
test("three series have separate inventory axis and missing stock is never a zero line", async () => {
  const { window, root, emit } = await setup("pge-projection-card");
  const data = snapshot();
  data.comparison = [
    { month: "2026-10", previous_kwh: "300", current_kwh: "100" },
    { month: "2026-11", previous_kwh: "400", current_kwh: null },
    { month: "2026-12", previous_kwh: null, current_kwh: null },
  ];
  data.planning.forecast = {
    rows: [
      { day: "2026-10-31", balance_kwh: "2000" },
      { day: "2026-11-30", balance_kwh: "1600" },
      { day: "2026-12-31", balance_kwh: null },
    ],
    complete: false,
    balance_kwh: null,
  };
  emit(data);
  assert.equal(root.querySelectorAll("svg polyline").length, 2);
  assert.equal(root.querySelectorAll("svg circle").length, 5);
  assert.match(root.textContent, /Pobór rok wcześniej/);
  assert.match(root.textContent, /prawa oś/);
  assert.match(root.textContent, /brak pełnej historii/);
  assert.doesNotMatch(root.textContent, /zapas wystarcza|Zapas wystarcza/);
  await window.happyDOM.close();
});
test("source wizard filters units and own entities, saves selected sources and preserves draft revision", async () => {
  const { window, card, root, calls, emit } = await setup("pge-settings-card");
  card.open("sources");
  const select = root.querySelector('[data-source="pv_power"]');
  assert.match(select.innerHTML, /sensor.pv/);
  assert.doesNotMatch(
    select.innerHTML,
    /sensor.pv_energy|sensor.alias_pv_power/,
  );
  select.value = "sensor.pv";
  emit({ ...snapshot(), revision: 4 });
  assert.equal(select.value, "sensor.pv");
  await card.saveSources();
  const sent = calls.find((c) => c.type === "pge_storage/put_energy");
  assert.equal(sent.revision, 3);
  assert.equal(
    JSON.stringify(sent.config.sources),
    JSON.stringify({ pv_power: "sensor.pv" }),
  );
  await window.happyDOM.close();
});
test("viewer cannot open editing controls", async () => {
  const { window, card, root } = await setup("pge-settings-card", false);
  assert.equal(root.getElementById("open-sources"), null);
  card.open("sources");
  assert.equal(root.querySelector("dialog").open, false);
  await window.happyDOM.close();
});
test("invoice editor preserves unsaved edits and optimistic revision, invoice zero is explicit", async () => {
  const { window, card, root, calls, emit } = await setup("pge-admin-panel");
  card._edit("invoice");
  root.getElementById("invoice").value = "0";
  root.getElementById("note").value = "Niezapisana zmiana";
  emit({ ...snapshot(), revision: 4 });
  await card._save();
  const command = calls.find((c) => c.type === "pge_storage/put");
  assert.equal(command.revision, 3);
  assert.equal(command.record.invoice_balance, "0");
  assert.equal(command.record.note, "Niezapisana zmiana");
  await window.happyDOM.close();
});
test("notes are escaped and failed invoice save keeps the draft", async () => {
  const { window, card, root, hass, emit } = await setup("pge-admin-panel");
  const data = snapshot();
  data.records[0].note = '<img src=x onerror="x">';
  emit(data);
  assert.equal(root.querySelector("img"), null);
  card._edit("invoice");
  root.getElementById("note").value = "Zachowaj";
  hass.callWS = async () => {
    throw new Error("Brak historii");
  };
  await card._save();
  assert.equal(root.getElementById("note").value, "Zachowaj");
  assert.match(root.getElementById("message").textContent, /Brak historii/);
  await window.happyDOM.close();
});
test("Lovelace picker registers every independent module and a visual tile editor", async () => {
  const { window, card } = await setup("pge-balance-card");
  assert.equal(window.customCards.length, 6);
  const editor = card.constructor.getConfigElement();
  editor.setConfig({ type: "custom:pge-balance-card", metric: "deficit" });
  assert.equal(
    editor.querySelector('select[data-key="metric"]').value,
    "deficit",
  );
  await window.happyDOM.close();
});

test("invoice history still paginates every record in the management dialog", async () => {
  const { window, root, emit } = await setup("pge-admin-panel");
  const data = snapshot();
  data.records = Array.from({ length: 101 }, (_, i) => ({
    ...data.records[0],
    id: `invoice-${i}`,
    note: `Faktura ${i}`,
  }));
  emit(data);
  assert.equal(root.querySelectorAll("#rows tr").length, 20);
  for (let i = 0; i < 5; i++) root.getElementById("next").click();
  assert.match(root.getElementById("rows").textContent, /Faktura 100/);
  assert.equal(root.getElementById("next").disabled, true);
  await window.happyDOM.close();
});

test("Energy defaults fill sources, preserve aggregate statistics and leave home automatic", async () => {
  const { window, card, root, hass } = await setup("pge-settings-card");
  hass.states["sensor.pv_second"] = {
    state: "100",
    attributes: { unit_of_measurement: "W" },
  };
  hass.callWS = async (command) =>
    command.type === "pge_storage/energy_defaults"
      ? {
          config: {
            sources: {
              pv_power: ["sensor.pv", "sensor.pv_second"],
              pv_energy: "sensor.pv_energy",
            },
            statistics: { pv_energy: ["sensor.pv_energy", "supplier:pv"] },
            directions: { grid: "import", battery: "discharge" },
            presence: { solar: true, battery: true },
            imported_from_energy: true,
            consumers: [{ name: "Pompa", statistic: "supplier:pump" }],
          },
          warnings: [],
        }
      : null;
  card.open("sources");
  await card.importPanel();
  assert.equal(
    root.querySelector('[data-source="pv_power"]').selectedOptions.length,
    2,
  );
  assert.match(
    root.querySelector('[data-source="home_power"]').textContent,
    /Oblicz z bilansu/,
  );
  const config = card.readSources();
  assert.equal(config.sources.home_power, undefined);
  assert.equal(config.statistics.pv_energy.length, 2);
  assert.equal(config.consumers[0].statistic, "supplier:pump");
  assert.equal(config.imported_from_energy, true);
  await window.happyDOM.close();
});
