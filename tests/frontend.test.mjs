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
  assert.equal(root.querySelectorAll("tbody tr").length, 20);
  assert.match(root.getElementById("pages").textContent, /101/);
  for (let i = 0; i < 5; i++) root.getElementById("next").click();
  assert.match(root.getElementById("rows").textContent, /Faktura 100/);
  assert.equal(root.getElementById("next").disabled, true);
  await window.happyDOM.close();
});
