import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";
import { Window } from "happy-dom";

const script = readFileSync(new URL("../custom_components/pge_storage/frontend/pge-storage-card.js", import.meta.url), "utf8");
const snapshot = () => ({
  entry_id: "test-entry", revision: 3, sources: { import: "sensor.import_total", export: "sensor.victron_export_total" }, source_values: { import: "7410", export: "10000" }, time_zone: "Europe/Warsaw", max_age_hours: 24,
  current: { start_day: "2026-03-15", source_value: "590", period_balance: "1540", carried_balance: "0", estimated_balance: "1540", available_energy: "1540", deficit: "0" },
  records: [{ id: "test-id", day: "2026-03-15", start_day: "2025-09-15", sample: { value: "-950", recorded_at: "2026-03-15T22:59:59+00:00", components: { import: { value: "4750", recorded_at: "2026-03-15T22:59:58+00:00" }, export: { value: "4750", recorded_at: "2026-03-15T22:59:59+00:00" } } }, period_balance: "-1950", invoice_balance: "0", invoice_difference: "950", estimated_before_invoice: "-950", correction: null, carried_balance: "0", note: "Faktura" }],
});

async function setup(admin = true) {
  const window = new Window();
  // Only evaluate our checked-in card. HTML/script evaluation stays disabled.
  runInNewContext(script, { window, HTMLElement: window.HTMLElement, customElements: window.customElements, Intl, Date, URL: window.URL, Blob: window.Blob, setTimeout, confirm: (...args) => window.confirm(...args) });
  const card = window.document.createElement("pge-storage-card");
  card.setConfig({ type: "custom:pge-storage-card" });
  window.document.body.append(card);
  const calls = [];
  let listener;
  let unsubscribed = false;
  const hass = {
    user: { is_admin: admin },
    connection: { subscribeMessage: async (callback, command) => {
      calls.push(command); listener = callback; callback(snapshot());
      return () => { unsubscribed = true; };
    } },
    callWS: async (command) => { calls.push(command); return null; },
  };
  card.hass = hass;
  await new Promise((resolve) => setImmediate(resolve));
  return { window, card, root: card.shadowRoot, calls, hass, emit: (data) => listener(data), unsubscribed: () => unsubscribed };
}

test("subscribes to HA and renders actual signed balances and table", async () => {
  const { window, root, calls, card, unsubscribed } = await setup();
  assert.equal(calls[0].type, "pge_storage/subscribe");
  assert.match(root.getElementById("metrics").textContent, /1.?540/);
  assert.match(root.getElementById("rows").textContent, /-1.?950/);
  assert.match(root.getElementById("period").textContent, /sensor.import_total/);
  assert.match(root.getElementById("period").textContent, /sensor.victron_export_total/);
  assert.match(root.getElementById("rows").textContent, /Import:.*Eksport:/s);
  assert.equal(root.querySelectorAll("svg rect.negative").length, 1);
  card.remove();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(unsubscribed(), true);
  await window.happyDOM.close();
});

test("renders untrusted notes as plain text and hides administration for viewers", async () => {
  const { window, root, emit } = await setup(false);
  const data = snapshot();
  data.records[0].note = '<img src=x onerror="alert(1)">';
  emit(data);
  assert.equal(root.querySelector("img"), null);
  assert.match(root.getElementById("rows").textContent, /<img/);
  assert.equal(root.querySelector("section[data-admin]").hidden, true);
  assert.equal(root.querySelector("td[data-admin]").hidden, true);
  await window.happyDOM.close();
});

test("invoice zero is sent explicitly as an accounting value", async () => {
  const { window, card, root, calls } = await setup();
  root.getElementById("day").value = "2026-03-16";
  root.getElementById("invoice").value = "0";
  await card._save();
  const command = calls.find((call) => call.type === "pge_storage/put");
  assert.equal(command.record.invoice_balance, "0");
  assert.equal(command.record.correction, null);
  assert.equal(command.revision, 3);
  await window.happyDOM.close();
});

test("live updates preserve unsaved edits and the revision when editing started", async () => {
  const { window, card, root, calls, emit } = await setup();
  card._edit("test-id");
  root.getElementById("note").value = "Niezapisana edycja";
  const data = snapshot();
  data.revision = 4;
  data.current.estimated_balance = "1590";
  emit(data);
  assert.equal(root.getElementById("note").value, "Niezapisana edycja");
  await card._save();
  const command = calls.find((call) => call.type === "pge_storage/put");
  assert.equal(command.revision, 3);
  assert.equal(command.record.id, "test-id");
  await window.happyDOM.close();
});

test("failed save keeps the editor and exposes an actionable server error", async () => {
  const { window, card, root, hass } = await setup();
  card._edit("test-id");
  root.getElementById("note").value = "Zachowaj";
  hass.callWS = async () => { throw new Error("Brak próbki Recorder"); };
  await card._save();
  assert.equal(root.getElementById("note").value, "Zachowaj");
  assert.match(root.getElementById("message").textContent, /Brak próbki Recorder/);
  await window.happyDOM.close();
});

test("history paginates all rows instead of capping the ledger size", async () => {
  const { window, root, emit } = await setup();
  const data = snapshot();
  data.records = Array.from({ length: 101 }, (_, index) => ({ ...data.records[0], id: `id-${index}`, note: `Faktura ${index}` }));
  emit(data);
  assert.equal(root.querySelectorAll("#rows tr").length, 20);
  assert.match(root.getElementById("pages").textContent, /101/);
  for (let i = 0; i < 5; i++) root.getElementById("next").click();
  assert.match(root.getElementById("rows").textContent, /Faktura 100/);
  assert.equal(root.getElementById("next").disabled, true);
  await window.happyDOM.close();
});

test("MAGAZYN shows usable energy and the raw counterpart, rounded to whole kWh", async () => {
  const { window, root, emit } = await setup();
  const data = snapshot();
  Object.assign(data.current, { available_energy: "2197.032", carried_balance: "2164", period_balance: "33.032", import_since_settlement_kwh: "134.76", export_since_settlement_kwh: "209.74", credited_since_settlement_kwh: "167.792" });
  emit(data);
  const metrics = root.getElementById("metrics").textContent;
  assert.match(metrics, /MAGAZYN — do odbioru/);
  assert.match(metrics, /2.?197 kWh/);
  assert.match(metrics, /2.?746 kWh/);
  assert.doesNotMatch(metrics, /2197,032|2.?197,032/);
  assert.match(root.getElementById("flow").textContent, /dodano 168 kWh/);
  await window.happyDOM.close();
});

test("monthly expansion shows five daily columns and preserves unknowns", async () => {
  const { window, root, card, hass } = await setup();
  hass.callWS = async () => ({ rows: [{ day: "2026-10-01", import_kwh: "5", withdrawn_kwh: "5", export_kwh: "10", credited_kwh: "8", net_kwh: "3", balance_kwh: "2167" }, { day: "2026-10-02", import_kwh: null, export_kwh: null, credited_kwh: null, net_kwh: null, balance_kwh: null, error: "Brak historii" }], basis: "Odczyty Recorder", updated_at: "2026-10-17T18:00:00+00:00" });
  const block = card._monthBlock("2026-10");
  assert.equal(block.open, false);
  await card._loadDaily("2026-10");
  assert.equal(block.open, true);
  const rows = block.querySelectorAll("[data-daily-rows] tr");
  assert.equal(rows[0].children.length, 5);
  assert.equal(rows[0].children[1].textContent, "8");
  assert.equal(rows[0].children[2].textContent, "5");
  assert.equal(rows[0].children[3].textContent, "3");
  assert.match(rows[0].children[4].textContent, /2.?167/);
  assert.doesNotMatch(block.textContent, /Import niepokryty|Czasy \/ uwagi/);
  assert.match(rows[1].textContent, /Brak historii/);
  assert.match(rows[1].textContent, /—/);
  await window.happyDOM.close();
});

test("live updates preserve an unsaved seasonal plan and its revision", async () => {
  const { window, root, card, emit, calls } = await setup();
  const data = snapshot();
  data.planning = { config: { anchor_id: null, lots: [], profile: [] }, target_day: "2027-03-31", inventory: null, forecast: null };
  emit(data);
  const input = root.querySelector('[data-profile="import"][data-month="1"]');
  input.value = "500";
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
  emit({ ...data, revision: 4 });
  assert.equal(input.value, "500");
  await card._savePlan();
  const command = calls.find((call) => call.type === "pge_storage/put_plan");
  assert.equal(command.revision, 3);
  assert.equal(command.planning.profile[0].import_kwh, "500");
  await window.happyDOM.close();
});


test("projection is a three-column stock depletion table with explicit history gaps", async () => {
  const { window, root, emit } = await setup();
  const data = snapshot();
  data.planning = {
    config: { anchor_id: "test-id", lots: [], profile: [] }, target_day: "2027-03-31",
    inventory: { balance_kwh: "200", expired_kwh: "0", lots: [] },
    missing_profile_months: [11],
    forecast: { complete: false, rows: [
      { day: "2026-10-31", period_import_kwh: "34.8", balance_kwh: "165.2", expired_kwh: "0", source_month: "2025-10" },
      { day: "2026-11-30", period_import_kwh: null, balance_kwh: null, expected_source_month: "2025-11" },
    ] },
  };
  emit(data);
  assert.equal(root.querySelectorAll("#forecast-table th").length, 3);
  const rows = root.querySelectorAll("#forecast-table tbody tr");
  assert.match(rows[0].textContent, /35.*165/);
  assert.match(rows[0].textContent, /2025-10/);
  assert.match(rows[1].textContent, /Brak historii.*2025-11.*—/);
  assert.doesNotMatch(root.getElementById("forecast-table").textContent, /Eksport licznika|Import licznika/);
  assert.match(root.getElementById("plan-summary").textContent, /bez przyszłych doładowań/);
  assert.equal(root.querySelector('[data-profile="export"]'), null);
  await window.happyDOM.close();
});
