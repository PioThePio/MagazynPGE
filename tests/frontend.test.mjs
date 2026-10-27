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
  let latest = snapshot();
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
        fn(latest);
        return () => {
          listeners.delete(fn);
          stopped++;
        };
      },
    },
    callWS: async (cmd) => {
      calls.push(cmd);
      if (cmd.type === "pge_storage/energy_period")
        return {
          period: cmd.period,
          anchor_day: cmd.anchor_day,
          label: cmd.anchor_day,
          values: latest.energy.today,
          consumers: latest.energy.consumers.map((c, i) => ({
            ...c,
            id: c.id || c.statistic || c.energy || c.power || String(i),
            period_kwh: c.today_kwh,
          })),
        };
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
      latest = data;
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
test("energy diagram shows live power and daily energy together without a toggle", async () => {
  const { window, root } = await setup("pge-energy-card");
  assert.match(root.querySelector(".node-pv strong").textContent, /2500 W/);
  assert.match(
    root.querySelector(".node-pv .node-energy").textContent,
    /6,6 kWh/,
  );
  assert.match(root.querySelector(".node-home strong").textContent, /1200 W/);
  assert.match(
    root.querySelector(".node-home .node-energy").textContent,
    /14,7 kWh/,
  );
  assert.match(
    root.querySelector(".node-grid").textContent,
    /Pobrano 8,2 kWh.*Oddano 1,6 kWh/,
  );
  assert.match(root.querySelector(".node-pge").textContent, /2197 kWh/);
  assert.equal(root.querySelector("[data-mode]"), null);
  await window.happyDOM.close();
});
test("month settlement expands to compact days with balance before net and real gaps", async () => {
  const { window, root } = await setup("pge-history-card");
  root.querySelector('[data-month="2026-10"] button').click();
  await tick();
  const rows = root.querySelectorAll('[data-days="2026-10"] tbody tr');
  assert.equal(rows.length, 2);
  assert.equal(rows[0].children.length, 5);
  assert.match(rows[0].textContent, /—/);
  assert.equal(rows[1].children[1].textContent, "5");
  assert.equal(rows[1].children[2].textContent, "8");
  assert.equal(rows[1].children[3].textContent, "2167");
  assert.equal(rows[1].children[4].textContent, "3");
  assert.ok(rows[0].children[0].textContent > rows[1].children[0].textContent);
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
  assert.equal(window.customCards.length, 9);
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
    root.querySelectorAll('[data-remove-source="pv_power"]').length,
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

test("missing PV is explicit, additional sources and removals preserve every remaining statistic", async () => {
  const { window, card, root, hass, emit } = await setup("pge-settings-card");
  const data = snapshot();
  data.energy.config = {
    sources: {
      pv_energy: ["sensor.solar_total_kwh", "sensor.pv_energy"],
      grid_power: "sensor.pv",
    },
    statistics: { pv_energy: ["sensor.solar_total_kwh", "sensor.pv_energy"] },
    consumers: [],
    directions: { grid: "import", battery: "charge" },
  };
  emit(data);
  card.open("sources");
  assert.equal(
    root.querySelectorAll('[data-remove-source="pv_energy"]').length,
    2,
  );
  assert.match(root.textContent, /sensor.solar_total_kwh.*BRAK ENCJI/s);
  assert.equal(root.querySelector('[data-source="grid_import_power"]'), null);
  assert.equal(root.querySelector('[data-source="grid_export_power"]'), null);
  let config = card.readSources();
  assert.equal(config.statistics.pv_energy.length, 2);
  assert.equal(config.sources.pv_energy.length, 2);
  root
    .querySelector(
      '[data-remove-source="pv_energy"][data-id="sensor.solar_total_kwh"]',
    )
    .click();
  config = card.readSources();
  assert.equal(config.sources.pv_energy, "sensor.pv_energy");
  assert.equal(config.statistics.pv_energy.length, 1);
  const mode = root.querySelector('[data-power-mode="grid"]');
  mode.value = "split";
  mode.dispatchEvent(new window.Event("change"));
  assert.ok(root.querySelector('[data-source="grid_import_power"]'));
  assert.equal(root.querySelector('[data-source="grid_power"]'), null);
  config = card.readSources();
  assert.equal(config.sources.grid_power, undefined);
  await window.happyDOM.close();
});
test("consumers are independent of flow and dashboard creation exposes a native edit link", async () => {
  const flow = await setup("pge-energy-card"),
    device = await setup("pge-consumers-card"),
    settings = await setup("pge-settings-card");
  const data = snapshot();
  data.energy.consumers = [
    {
      name: "Pompa",
      today_kwh: "7.8",
      power_w: "900",
      energy: "sensor.pv_energy",
    },
  ];
  data.revision = 4;
  flow.emit(data);
  device.emit(data);
  await tick();
  assert.doesNotMatch(flow.root.textContent, /Pompa/);
  assert.match(device.root.textContent, /Pompa/);
  assert.match(device.root.textContent, /7,8 kWh/);
  assert.match(device.root.textContent, /900 W/);
  settings.hass.callWS = async (command) => {
    assert.equal(command.type, "pge_storage/create_dashboard");
    return { created: true, url: "/pge-energia-abc/magazyn" };
  };
  await settings.card.createDashboard();
  assert.equal(
    settings.root.querySelector("#open-dashboard").getAttribute("href"),
    "/pge-energia-abc/magazyn",
  );
  settings.emit({ ...snapshot(), revision: 4 });
  assert.ok(settings.root.querySelector("#open-dashboard"));
  for (const value of [flow, device, settings])
    await value.window.happyDOM.close();
});

test("PV provenance pairs native energy and power, while battery capacity previews without a stored sensor", async () => {
  const { window, card, root, hass, emit } = await setup("pge-settings-card");
  hass.states["sensor.soc"] = {
    state: "15",
    attributes: { unit_of_measurement: "%", friendly_name: "Victron SOC" },
  };
  const data = snapshot();
  data.energy.config = {
    sources: {
      pv_energy: ["sensor.solar_total_kwh", "sensor.pv_energy"],
      pv_power: "sensor.pv",
      battery_soc: "sensor.soc",
    },
    consumers: [],
    statistics: { pv_energy: ["sensor.solar_total_kwh", "sensor.pv_energy"] },
    directions: { grid: "import", battery: "discharge" },
  };
  data.energy.import_report = [
    {
      type: "solar",
      name: "Druga instalacja",
      energy: [
        {
          id: "sensor.solar_total_kwh",
          name: "Druga instalacja kWh",
          role: "pv_energy",
          origin: { path: "energy_sources[0].stat_energy_from" },
        },
      ],
      power: [],
      soc: [],
    },
    {
      type: "solar",
      name: "MPPT250/70",
      energy: [
        {
          id: "sensor.pv_energy",
          role: "pv_energy",
          name: "MPPT yield",
          origin: { path: "energy_sources[1].stat_energy_from" },
        },
      ],
      power: [
        {
          id: "sensor.pv",
          role: "pv_power",
          name: "MPPT power",
          origin: { path: "energy_sources[1].stat_rate" },
        },
      ],
      soc: [],
    },
  ];
  emit(data);
  card.open("sources");
  assert.match(
    root.querySelector("#pv-import-report").textContent,
    /Brak pomiaru w Energii → 0 W/,
  );
  assert.match(
    root.querySelector("#pv-import-report").textContent,
    /MPPT power/,
  );
  assert.match(
    root.querySelector('[data-remove-source="pv_power"]').parentElement
      .textContent,
    /Źródło: Energia.*MPPT250\/70.*Moc/,
  );
  assert.equal(root.querySelector('[data-source="battery_stored"]').value, "");
  const capacity = root.querySelector("[data-capacity]");
  capacity.value = "10";
  capacity.dispatchEvent(new window.Event("input"));
  assert.match(
    root.querySelector("#battery-estimate").textContent,
    /15%.*10 kWh = 1,5 kWh/,
  );
  const saved = card.readSources();
  assert.equal(saved.battery_capacity_kwh, "10");
  assert.equal(saved.sources.battery_stored, undefined);
  assert.match(
    root.querySelector('[data-source="battery_stored"]').textContent,
    /Z SOC i pojemności/,
  );
  await window.happyDOM.close();
});

test("consumer folders exclude children from tracked totals and preserve decimal precision", async () => {
  const { window, root, emit } = await setup("pge-consumers-card");
  const data = snapshot();
  data.revision = 8;
  data.energy.values.home_power = "1000";
  data.energy.today.home_energy = "12";
  data.energy.consumers = [
    {
      id: "ac",
      name: "AC",
      power: "sensor.ac",
      energy: "sensor.ac_e",
      power_w: "500.2",
      today_kwh: "6.2",
    },
    {
      id: "down",
      parent_id: "ac",
      name: "AC-Dół",
      power: "sensor.down",
      energy: "sensor.down_e",
      power_w: "200.1",
      today_kwh: "2.1",
    },
    {
      id: "up",
      parent_id: "ac",
      name: "AC-Góra",
      power: "sensor.up",
      energy: "sensor.up_e",
      power_w: "300.1",
      today_kwh: "4.1",
    },
    {
      id: "fridge",
      name: "Lodówka",
      power: "sensor.fridge",
      energy: "sensor.fridge_e",
      power_w: "100",
      today_kwh: "1",
    },
  ];
  emit(data);
  await tick();
  assert.match(
    root.querySelector(".consumer-summary").textContent,
    /600 W.*7,2 kWh/,
  );
  assert.match(
    root.querySelector(".untracked").textContent,
    /400 W.*4,8 kWh/,
  );
  assert.match(root.textContent, /200 W/);
  assert.equal(root.querySelectorAll(".device").length, 5);
  assert.equal(root.querySelectorAll("[data-folder]").length, 0);
  assert.equal(root.querySelectorAll(".tree-stem").length, 2);
  assert.match(root.querySelector(".consumer-total").textContent, /1.?000 W/);
  await window.happyDOM.close();
});
test("period navigation changes energy while current power and arrow direction remain live", async () => {
  const { window, card, root, hass, emit } = await setup("pge-energy-card");
  hass.callWS = async (cmd) => ({
    period: cmd.period,
    label: cmd.anchor_day,
    values: {
      pv_energy: cmd.period === "year" ? "1234" : "20",
      home_energy: "30",
      grid_import_energy: "15",
      grid_export_energy: "5",
      pge_credited_energy: "4",
      pge_withdrawn_energy: "10",
    },
    consumers: [],
  });
  const data = snapshot();
  data.revision = 9;
  data.energy.values.grid_import_power = "0";
  data.energy.values.grid_export_power = "500";
  data.energy.values.battery_charge_power = "50";
  data.energy.values.battery_discharge_power = "0";
  data.energy.pv_arrays = [
    {
      id: "one",
      name: "Pierwsza instalacja",
      power_w: "1000",
      power_entity: "sensor.pv",
    },
    { id: "two", name: "Druga instalacja", power_w: "1500" },
  ];
  emit(data);
  await tick();
  assert.match(root.querySelector(".node-grid strong").textContent, /-500 W/);
  assert.ok(
    root.querySelector('[data-flow="grid"]').hasAttribute("marker-start"),
  );
  assert.ok(
    root.querySelector('[data-flow="battery"]').hasAttribute("marker-end"),
  );
  assert.equal(root.querySelectorAll(".pv-installation").length, 2);
  root.querySelector('[data-period="year"]').click();
  await tick();
  assert.match(
    root.querySelector(".node-pv .node-energy").textContent,
    /1.?234,0 kWh/,
  );
  assert.match(root.querySelector(".node-pv strong").textContent, /2500 W/);
  const old = card.anchor;
  root.querySelector('[data-shift="-1"]').click();
  await tick();
  assert.equal(Number(card.anchor.slice(0, 4)), Number(old.slice(0, 4)) - 1);
  assert.equal(root.querySelectorAll("[data-period]").length, 4);
  assert.doesNotMatch(root.querySelector(".flow-map").textContent, /Dziś/);
  await window.happyDOM.close();
});
test("battery Ah conversion requires nominal voltage and settings retain parent references", async () => {
  const { window, card, root, hass, emit } = await setup("pge-settings-card");
  hass.states["sensor.soc"] = {
    state: "50",
    attributes: { unit_of_measurement: "%" },
  };
  const data = snapshot();
  data.energy.config = {
    sources: { battery_soc: "sensor.soc" },
    consumers: [
      { id: "ac", name: "AC", energy: "sensor.ac" },
      { id: "child", parent_id: "ac", name: "AC-Dół", energy: "sensor.child" },
    ],
  };
  emit(data);
  card.open("sources");
  const mode = root.querySelector("[data-capacity-mode]");
  mode.value = "ah";
  mode.dispatchEvent(new window.Event("change"));
  root.querySelector("[data-capacity-ah]").value = "99";
  root
    .querySelector("[data-capacity-ah]")
    .dispatchEvent(new window.Event("input"));
  assert.match(
    root.querySelector("#battery-estimate").textContent,
    /napięcie nominalne/,
  );
  root.querySelector("[data-voltage]").value = "51.2";
  root.querySelector("[data-voltage]").dispatchEvent(new window.Event("input"));
  assert.match(root.querySelector("#battery-estimate").textContent, /5,07 kWh/);
  assert.match(root.querySelector("#battery-estimate").textContent, /2,53 kWh/);
  const saved = card.readSources();
  assert.equal(saved.battery_capacity_kwh, null);
  assert.equal(saved.battery_capacity_ah, "99");
  assert.equal(saved.battery_voltage, "51.2");
  assert.equal(saved.consumers[1].parent_id, "ac");
  await window.happyDOM.close();
});

test("live power updates preserve mounted cards, controls and consumer rows", async () => {
  const { window, root, emit } = await setup("pge-consumers-card");
  await tick();
  const shell = root.querySelector("ha-card");
  const control = root.querySelector("[data-anchor]");
  const untracked = root.querySelector(".devices > .device.untracked");
  assert.ok(untracked);
  for (let i = 0; i < 5; i++) {
    const data = snapshot();
    data.energy.values.home_power = String(1200 + i);
    emit(data);
    assert.equal(root.querySelector("ha-card"), shell);
    assert.equal(root.querySelector("[data-anchor]"), control);
    assert.equal(root.querySelector(".untracked"), untracked);
  }
  window.happyDOM.abort();
});

test("consumer sort includes untracked and offers time-window means without breaking folders", async () => {
  const { window, root, emit } = await setup("pge-consumers-card");
  const data = snapshot();
  data.revision = 15;
  data.energy.values.home_power = "1000";
  data.energy.consumers = [
    { id: "a", name: "Alfa", power: "sensor.a", energy: "sensor.a_e", power_w: "600", today_kwh: "2" },
    { id: "b", name: "Beta", power: "sensor.b", energy: "sensor.b_e", power_w: "100", today_kwh: "8" },
  ];
  data.energy.power_windows = Object.fromEntries([1,5,10,15].map(seconds => [String(seconds), {
    home_power_w: 1000, tracked_power_w: 800, untracked_power_w: 200,
    consumers: {a: 100, b: 700}, covered_seconds: seconds,
  }]));
  emit(data);
  await tick();
  const names = () => [...root.querySelectorAll(".devices > .device .device-name")].map(n => n.textContent);
  assert.deepEqual(names(), ["Alfa", "Nieśledzone zużycie", "Beta"]);
  root.querySelector('[data-sort="name"]').click();
  assert.deepEqual(names(), ["Alfa", "Beta", "Nieśledzone zużycie"]);
  assert.equal(root.querySelector('[data-sort="name"]').parentElement.getAttribute("aria-sort"), "ascending");
  root.querySelector('[data-sort="name"]').click();
  assert.deepEqual(names(), ["Nieśledzone zużycie", "Beta", "Alfa"]);
  root.querySelector('[data-sort="average"]').click();
  assert.deepEqual(names(), ["Beta", "Nieśledzone zużycie", "Alfa"]);
  assert.equal(root.querySelector("[data-average]").value, "5");
  assert.equal(root.querySelectorAll("[data-average] option").length, 4);
  root.querySelector("[data-average]").value = "15";
  root.querySelector("[data-average]").dispatchEvent(new window.Event("change"));
  assert.match(root.querySelector('[data-consumer-id="b"] .device-average').textContent, /700 W/);
  assert.match(root.querySelector(".untracked .device-average").textContent, /200 W/);
  root.querySelector('[data-sort="energy"]').click();
  assert.equal(names()[0], "Beta");
  assert.equal(root.querySelector("[data-average]").value, "15");
  await window.happyDOM.close();
});

test("diagram uses aligned mature power windows and has no timing footer", async () => {
  const { window, root, emit } = await setup("pge-energy-card");
  const data = snapshot();
  data.energy.power_windows = {"15": {covered_seconds: 15,
    values: {pv_power: 1800, home_power: 700, grid_import_power: 0, grid_export_power: 1100},
    pv_arrays: {},
  }};
  emit(data);
  assert.equal(root.querySelector("[data-flow-average]").value, "10");
  root.querySelector("[data-flow-average]").value = "15";
  root.querySelector("[data-flow-average]").dispatchEvent(new window.Event("change"));
  assert.match(root.querySelector(".node-pv strong").textContent, /1800 W/);
  assert.match(root.querySelector(".node-home strong").textContent, /700 W/);
  assert.equal(root.querySelector(".period-note"), null);
  await window.happyDOM.close();
});

test("untracked row opens its own HA entity and column headings stay inside the table", async () => {
  const { window, card, root, emit } = await setup("pge-consumers-card");
  const data = snapshot();
  data.entities.untracked_power = "sensor.pge_untracked";
  emit(data);
  let selected;
  card.addEventListener("hass-more-info", event => {selected = event.detail.entityId;});
  root.querySelector('.untracked .device-name').click();
  assert.equal(selected, "sensor.pge_untracked");
  assert.equal(root.querySelectorAll('.device-header [data-sort]').length, 4);
  assert.equal(root.querySelectorAll('.sort-options').length, 0);
  assert.deepEqual([...root.querySelectorAll('.device-header button')].map(n => n.textContent.replace(/[▴▾]/g, '').trim()),
    ["Nazwa", "Moc", "Średnia", "Energia"]);
  await window.happyDOM.close();
});

test("diagram freezes a complete frame between source reports and PGE is connected below grid", async () => {
  const { window, root, emit } = await setup("pge-energy-card");
  const data = snapshot();
  const energy = structuredClone(data.energy);
  data.energy.diagram_frame = {sequence: 1, energy, available_energy: "2000"};
  emit(data);
  assert.match(root.querySelector(".node-home strong").textContent, /1200 W/);
  data.energy.values.home_power = "9999";
  emit(data);
  assert.match(root.querySelector(".node-home strong").textContent, /1200 W/);
  data.energy.diagram_frame = {sequence: 2, energy: {...energy, values: {...energy.values, home_power: "900"}}, available_energy: "1999"};
  emit(data);
  assert.match(root.querySelector(".node-home strong").textContent, /900 W/);
  const grid = root.querySelector(".node-grid"), pge = root.querySelector(".node-pge");
  assert.equal(grid.style.left, pge.style.left);
  assert.ok(parseFloat(pge.style.top) > parseFloat(grid.style.top));
  const link = root.querySelector('[data-flow="pge"]');
  assert.equal(link.getAttribute("d"), "M150 375V398");
  assert.equal(link.hasAttribute("marker-start"), false);
  assert.equal(link.hasAttribute("marker-end"), false);
  data.energy.hourly_current = {start:"2026-10-26T12:00:00Z", end:"2026-10-26T13:00:00Z", known:true, balance_kwh:"2", net_kwh:"1.6"};
  emit(data);
  assert.match(root.querySelector(".hour-buffer").textContent, /\+2/);
  assert.doesNotMatch(root.querySelector(".hour-buffer").textContent, /Wpływ/);
  await window.happyDOM.close();
});

test("compact hour can be hidden, opens its entity, and rings use power shares", async () => {
  const {window,card,root,emit}=await setup("pge-energy-card");
  const data=snapshot();
  data.entities.hourly_balance="sensor.hour";
  data.energy.hourly_current={known:true,balance_kwh:"-0.42",net_kwh:"0.336"};
  data.energy.values={pv_power:200,grid_import_power:700,grid_export_power:0,battery_discharge_power:100,battery_charge_power:0,home_power:1000};
  data.energy.pv_arrays=[{id:"low",power_entity:"sensor.low",name:"MPPT",power_w:100},{id:"high",power_entity:"sensor.high",name:"Solar Power",power_w:100}];
  data.energy.config.pv_order=["sensor.high","sensor.low"];
  emit(data);
  assert.match(root.querySelector(".hour-buffer").textContent,/-0,42/);
  let entity;
  card.addEventListener("hass-more-info",event=>entity=event.detail.entityId);
  root.querySelector("[data-hour-info]").click();
  assert.equal(entity,"sensor.hour");
  assert.match(root.querySelector(".node-home").getAttribute("style"),/20%.*30%/);
  assert.equal(root.querySelector(".node-pv").style.left,root.querySelector(".node-home").style.left);
  assert.match(root.querySelector(".pv-left .pv-installation").textContent,/Solar Power/);
  assert.equal(root.querySelectorAll(".pv-right .pv-installation").length,0);
  assert.equal(root.querySelectorAll(".period-picker .chip").length,0);
  card.setConfig({type:"custom:pge-energy-card",show_hour:false});
  assert.equal(root.querySelector(".hour-buffer"),null);
  await window.happyDOM.close();
});

test("battery settings save minute windows, Victron number selectors, display mode and PV order", async () => {
  const {window,card,root,hass,emit}=await setup("pge-settings-card");
  hass.states["number.minimum"]={state:"20",attributes:{unit_of_measurement:"%",friendly_name:"Minimum SOC"}};
  const data=snapshot();
  data.energy.config.sources.pv_power=["sensor.pv","sensor.alias_pv_power"];
  data.energy.config.pv_order=["sensor.pv","sensor.alias_pv_power"];
  emit(data);
  root.querySelector("#open-sources").click();
  root.querySelector('[data-battery-option="min_soc_entity"]').value="number.minimum";
  root.querySelector("[data-eta-average]").value="15";
  root.querySelector("[data-flow-mode]").value="latest";
  root.querySelector("[data-show-hour]").checked=false;
  root.querySelector('[data-pv-down="sensor.pv"]').click();
  const saved=card.readSources();
  assert.equal(saved.battery_forecast.min_soc_entity,"number.minimum");
  assert.equal(saved.battery_forecast.average_minutes,15);
  assert.equal(saved.flow_mode,"latest");
  assert.equal(saved.show_hour,false);
  assert.deepEqual(Array.from(saved.pv_order),["sensor.alias_pv_power","sensor.pv"]);
  await window.happyDOM.close();
});

test("current hour leaves the grid power arrow unobstructed", async () => {
  const {window,root,emit}=await setup("pge-energy-card");
  const data=snapshot();
  data.energy.values.grid_import_power=600;
  data.energy.values.grid_export_power=0;
  data.energy.hourly_current={known:true,balance_kwh:"0.37"};
  emit(data);
  const line=root.querySelector('[data-flow="grid"]');
  assert.equal(line.getAttribute("d"),"M233 290H307");
  assert.ok(line.hasAttribute("marker-end"));
  assert.match(root.querySelector("style:last-of-type").textContent,/\.hour-buffer\{[^}]*top:31%/);
  assert.match(root.querySelector(".hour-buffer").textContent,/\+0,37/);
  await window.happyDOM.close();
});
