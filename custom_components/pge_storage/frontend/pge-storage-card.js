/* Magazyn PGE: self-contained Lovelace card; no external scripts or CDN. */
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
const fmt = (value) => value == null ? "—" : new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 3 }).format(Number(value));
const dayLabel = (day) => day ? day.split("-").reverse().join(".") : "—";
const stampLabel = (stamp) => new Date(stamp).toLocaleString("pl-PL", { timeZone: "Europe/Warsaw" });

class PGEStorageCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._page = 0;
    this._generation = 0;
    this._config = {};
  }

  setConfig(config) {
    this._config = { ...config };
    this._stop();
    this._build();
    this._connect();
  }

  set hass(hass) {
    this._hass = hass;
    this._adminVisibility();
    this._connect();
  }

  connectedCallback() { this._connect(); }
  disconnectedCallback() { this._stop(); }
  getCardSize() { return 12; }
  static getStubConfig() { return { title: "Wirtualny magazyn PGE" }; }

  _stop() {
    this._generation += 1;
    this._unsubscribe?.();
    this._unsubscribe = null;
    this._attemptedConnection = null;
  }

  async _connect() {
    if (!this.isConnected || !this._hass || !this.shadowRoot.querySelector("ha-card")) return;
    const connection = this._hass.connection;
    if (this._attemptedConnection === connection) return;
    this._attemptedConnection = connection;
    const generation = this._generation;
    try {
      const command = { type: "pge_storage/subscribe" };
      if (this._config.entry_id) command.entry_id = this._config.entry_id;
      const unsubscribe = await connection.subscribeMessage((data) => {
        if (generation !== this._generation) return;
        this._data = data;
        this._renderData();
      }, command);
      if (generation !== this._generation || !this.isConnected) unsubscribe();
      else this._unsubscribe = unsubscribe;
    } catch (error) {
      this._message(error.message || String(error), true);
    }
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block}*{box-sizing:border-box}ha-card{padding:24px;color:var(--primary-text-color);overflow:hidden}
        h1{font-size:1.4rem;margin:0 0 8px}h2{font-size:1.1rem;margin:24px 0 12px}.muted{color:var(--secondary-text-color);font-size:.9rem;line-height:1.5}
        .metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin:20px 0}.metric{background:var(--secondary-background-color,#eee);border-radius:12px;padding:16px}.value{font-size:1.5rem;font-weight:600;margin-top:6px}
        .scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{padding:12px 10px;border-bottom:1px solid var(--divider-color,#ddd);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{font-weight:600}caption{text-align:left;margin:10px 0}
        button{background:var(--primary-color,#087f8c);color:var(--text-primary-color,#fff);border:0;border-radius:7px;padding:10px 14px;cursor:pointer;font:inherit}button.secondary{background:var(--secondary-background-color,#eee);color:var(--primary-text-color)}button.danger{background:#a42828;color:white}button:disabled{opacity:.5;cursor:wait}
        .tools{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:14px 0}.notice{border-left:4px solid var(--primary-color,#087f8c);padding:12px;margin:12px 0;background:var(--secondary-background-color,#eee)}.error{border-left-color:#b3261e} .notice:empty{display:none}
        form{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}label{display:flex;flex-direction:column;gap:7px;font-size:.9rem}input,textarea{font:inherit;padding:10px;border-radius:6px;border:1px solid var(--divider-color,#aaa);background:var(--card-background-color,#fff);color:var(--primary-text-color)}textarea{resize:vertical}.full{grid-column:1/-1}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.8rem}.chart{min-width:480px}.chart svg{display:block;width:100%;max-height:260px}.chart text{fill:var(--secondary-text-color,#555);font-size:11px}.positive{fill:var(--primary-color,#087f8c)}.negative{fill:#b55235}[hidden]{display:none!important}
      </style>
      <ha-card>
        <h1>${esc(this._config.title || "Wirtualny magazyn PGE")}</h1>
        <div class="muted">Dwa liczniki sieci: eksport × 0,8 − import · granice: koniec dnia w Europe/Warsaw</div>
        <div id="message" class="notice" role="status" aria-live="polite"></div>
        <div id="metrics" class="metrics"></div>
        <div id="period" class="muted">Łączenie z rejestrem…</div>
        <div id="warnings" class="notice"></div>
        <h2>Historia rozliczeń</h2>
        <div class="muted">Pierwsza data to punkt początkowy. Bilans okresu obejmuje energię po poprzedniej dacie, do końca kolejnej daty włącznie.</div>
        <div class="scroll"><table><caption>Wszystkie wartości energii w kWh. Znak minus oznacza niedobór.</caption>
          <thead><tr><th>Koniec dnia</th><th>Import / eksport</th><th>Bilans obliczony</th><th>Bilans okresu</th><th>Szacunek przed fakturą</th><th>Saldo z faktury</th><th>Różnica faktura − HA</th><th>Korekta</th><th>Niedobór z faktury</th><th>Saldo przeniesione</th><th>Odczyty Recorder</th><th>Uwagi</th><th data-admin>Akcje</th></tr></thead>
          <tbody id="rows"></tbody></table></div>
        <div class="tools"><button id="previous" class="secondary">Poprzednie</button><span id="pages" class="muted"></span><button id="next" class="secondary">Następne</button></div>
        <h2>Porównanie okresów</h2>
        <div class="muted">Bilans pomiarowy ostatnich 12 zamkniętych okresów. Daty nie muszą przypadać co pół roku.</div>
        <div class="scroll"><div id="chart" class="chart"></div></div>
        <section data-admin>
          <h2 id="editor-title">Dodaj datę rozliczenia</h2>
          <form id="editor">
            <label>Data rozliczenia (koniec dnia)<input id="day" name="day" type="date" required></label>
            <label>Saldo po fakturze [kWh], opcjonalnie<input id="invoice" name="invoice_balance" type="number" step="any" placeholder="np. 0 lub 350,5 lub -120"></label>
            <label>Korekta szacunku [kWh], opcjonalnie<input id="correction" name="correction" type="number" step="any" placeholder="np. -25"></label>
            <label>Niedobór rozliczony na fakturze [kWh]<input id="shortfall" name="invoice_shortfall" type="number" min="0" step="any" placeholder="Informacyjnie, np. 950"></label>
            <label class="full">Uwagi<textarea id="note" name="note" maxlength="2000" rows="2"></textarea></label>
            <div class="muted full">Podaj saldo z faktury albo korektę. Saldo z faktury zastępuje szacunek; korekta jest do niego dodawana. Zero wpisz jawnie. Puste pole oznacza brak informacji. Niedobór rozliczony na fakturze jest informacyjny: przy wyzerowaniu wpisz saldo 0, aby nie odjąć go ponownie. W pierwszym wpisie podaj znane saldo początkowe.</div>
            <div class="tools full"><button type="submit">Zapisz rozliczenie</button><button id="cancel" type="button" class="secondary">Nowy wpis / anuluj edycję</button><button id="diagnose" type="button" class="secondary">Sprawdź historię dla daty</button></div>
          </form>
          <pre id="diagnosis" hidden></pre>
          <div class="tools"><button id="export" class="secondary">Pobierz kopię JSON</button><button id="import" class="secondary">Przywróć kopię JSON</button><input id="import-file" type="file" accept="application/json,.json" hidden></div>
          <div class="muted">Przywracanie zastępuje cały rejestr tego magazynu. Przed zmianami pobierz kopię. Zmiana historycznej daty wymaga dostępnej historii dla nowej daty.</div>
        </section>
      </ha-card>`;
    const root = this.shadowRoot;
    root.getElementById("editor").addEventListener("submit", (e) => { e.preventDefault(); this._save(); });
    root.getElementById("editor").addEventListener("input", () => { this._editRevision ??= this._data?.revision; });
    root.getElementById("cancel").onclick = () => this._resetEditor();
    root.getElementById("diagnose").onclick = () => this._diagnose();
    root.getElementById("export").onclick = () => this._export();
    root.getElementById("import").onclick = () => root.getElementById("import-file").click();
    root.getElementById("import-file").onchange = (event) => this._import(event);
    root.getElementById("previous").onclick = () => { this._page = Math.max(0, this._page - 1); this._renderData(); };
    root.getElementById("next").onclick = () => { this._page += 1; this._renderData(); };
    root.getElementById("rows").onclick = (event) => {
      const button = event.target.closest("button[data-id]");
      if (!button || this._busy) return;
      if (button.dataset.action === "edit") this._edit(button.dataset.id);
      if (button.dataset.action === "delete") this._delete(button.dataset.id);
      if (button.dataset.action === "refresh") this._refresh(button.dataset.id);
    };
    this._adminVisibility();
  }

  _adminVisibility() {
    for (const element of this.shadowRoot.querySelectorAll("[data-admin]")) element.hidden = !this._hass?.user?.is_admin;
  }

  _message(message, error = false) {
    const element = this.shadowRoot.getElementById("message");
    if (!element) return;
    element.textContent = message;
    element.className = `notice${error ? " error" : ""}`;
  }

  _renderData() {
    if (!this._data) return;
    const { current, records } = this._data;
    const root = this.shadowRoot;
    const fields = [["estimated_balance", "Szacunkowe saldo"], ["available_energy", "Energia dostępna"], ["deficit", "Niedobór"], ["period_balance", "Bilans bieżącego okresu"], ["carried_balance", "Saldo przeniesione"]];
    root.getElementById("metrics").innerHTML = fields.map(([key, title]) => `<div class="metric"><div>${title}</div><div class="value">${fmt(current[key])} <small>kWh</small></div></div>`).join("");
    root.getElementById("period").textContent = `Import: ${this._data.sources?.import || "—"} (${fmt(this._data.source_values?.import)} kWh). Eksport: ${this._data.sources?.export || "—"} (${fmt(this._data.source_values?.export)} kWh). Bieżący okres: ${current.start_day ? `po ${dayLabel(current.start_day)}, do teraz` : "brak punktu początkowego"}.`;
    const warnings = [];
    if (this._data.loaded === false) warnings.push("Integracja została wyłączona lub jest przeładowywana. Bieżące saldo jest niedostępne.");
    if (!records.length) warnings.push("Dodaj pierwszą datę jako punkt początkowy; później dodaj kolejne rozliczenia.");
    else if (current.carried_balance == null) warnings.push("Brak znanego salda początkowego lub faktury. Bilans energii jest dostępny, ale saldo magazynu pozostaje nieznane.");
    if (records.some((row) => row.correction != null && !row.correction_applied)) warnings.push("Co najmniej jednej korekty nie można zastosować, bo wcześniejsze saldo jest nieznane. Uzupełnij saldo z faktury.");
    if (this._data.source_error) warnings.push(this._data.source_error);
    root.getElementById("warnings").textContent = warnings.join(" ");
    const pages = Math.max(1, Math.ceil(records.length / 20));
    this._page = Math.min(this._page, pages - 1);
    root.getElementById("pages").textContent = `Strona ${this._page + 1} z ${pages} · wpisów: ${records.length}`;
    root.getElementById("previous").disabled = this._page === 0;
    root.getElementById("next").disabled = this._page + 1 >= pages;
    root.getElementById("rows").innerHTML = records.slice(this._page * 20, (this._page + 1) * 20).map((row) => `<tr>
      <td>${esc(dayLabel(row.day))}${row.start_day ? `<br><small>po ${esc(dayLabel(row.start_day))}</small>` : "<br><small>Punkt początkowy</small>"}</td>
      <td>${fmt(row.sample.components?.import?.value)} / ${fmt(row.sample.components?.export?.value)}</td><td>${fmt(row.sample.value)}</td><td>${fmt(row.period_balance)}</td><td>${fmt(row.estimated_before_invoice)}</td><td>${fmt(row.invoice_balance)}</td><td>${fmt(row.invoice_difference)}</td><td>${fmt(row.correction)}</td><td>${fmt(row.invoice_shortfall)}</td><td>${fmt(row.carried_balance)}</td>
      <td>Import: ${esc(stampLabel(row.sample.components?.import?.recorded_at || row.sample.recorded_at))}<br>Eksport: ${esc(stampLabel(row.sample.components?.export?.recorded_at || row.sample.recorded_at))}</td><td title="${esc(row.note)}">${esc(row.note)}</td>
      <td data-admin><button class="secondary" data-action="edit" data-id="${esc(row.id)}">Edytuj</button> <button class="secondary" data-action="refresh" data-id="${esc(row.id)}">Odczytaj ponownie</button> <button class="danger" data-action="delete" data-id="${esc(row.id)}">Usuń</button></td>
      </tr>`).join("") || '<tr><td colspan="13">Brak zapisanych dat.</td></tr>';
    root.getElementById("chart").innerHTML = this._chart(records.filter((r) => r.period_balance != null).slice(-12));
    this._adminVisibility();
  }

  _chart(rows) {
    if (!rows.length) return '<p class="muted">Wykres pojawi się po dodaniu co najmniej dwóch dat.</p>';
    const width = Math.max(600, rows.length * 95);
    const scale = 75 / Math.max(1, ...rows.map((r) => Math.abs(Number(r.period_balance))));
    return `<svg viewBox="0 0 ${width} 245" role="img" aria-label="Porównanie bilansów zamkniętych okresów w kWh"><line x1="0" y1="115" x2="${width}" y2="115" stroke="currentColor" opacity=".4"/>${rows.map((row, index) => {
      const value = Number(row.period_balance), height = Math.abs(value) * scale;
      const center = (index + 0.5) * width / rows.length;
      return `<g><title>Po ${esc(row.start_day)} do ${esc(row.day)}: ${esc(row.period_balance)} kWh</title><rect class="${value >= 0 ? "positive" : "negative"}" x="${center - 23}" y="${value >= 0 ? 115 - height : 115}" width="46" height="${Math.max(1, height)}" rx="3"/><text x="${center}" y="${value >= 0 ? 105 - height : 132 + height}" text-anchor="middle">${esc(fmt(row.period_balance))}</text><text x="${center}" y="225" text-anchor="middle">${esc(dayLabel(row.day))}</text></g>`;
    }).join("")}</svg>`;
  }

  async _call(action, values = {}, write = false) {
    if (!this._data) throw new Error("Poczekaj na wczytanie rejestru.");
    if (this._data.loaded === false) throw new Error("Integracja nie jest uruchomiona. Włącz ją w ustawieniach HA.");
    return this._hass.callWS({ type: `pge_storage/${action}`, entry_id: this._data.entry_id, ...(write ? { revision: this._data.revision } : {}), ...values });
  }

  async _run(operation, success) {
    if (this._busy) return false;
    this._busy = true;
    this._message("Przetwarzanie…");
    try {
      await operation();
      this._message(success);
      return true;
    } catch (error) {
      this._message(error.message || String(error), true);
      return false;
    } finally { this._busy = false; }
  }

  _resetEditor() {
    this._editing = null;
    this._editRevision = null;
    this.shadowRoot.getElementById("editor").reset();
    this.shadowRoot.getElementById("editor-title").textContent = "Dodaj datę rozliczenia";
  }

  _edit(id) {
    const row = this._data.records.find((r) => r.id === id);
    if (!row) return;
    this._editing = id;
    this._editRevision = this._data.revision;
    for (const [field, value] of [["day", row.day], ["invoice", row.invoice_balance], ["correction", row.correction], ["shortfall", row.invoice_shortfall], ["note", row.note]]) this.shadowRoot.getElementById(field).value = value ?? "";
    this.shadowRoot.getElementById("editor-title").textContent = `Edytuj rozliczenie ${dayLabel(row.day)}`;
    this.shadowRoot.getElementById("day").focus();
  }

  async _save() {
    const root = this.shadowRoot;
    if (!root.getElementById("editor").reportValidity()) return;
    const record = { day: root.getElementById("day").value, invoice_balance: root.getElementById("invoice").value || null, correction: root.getElementById("correction").value || null, invoice_shortfall: root.getElementById("shortfall").value || null, note: root.getElementById("note").value };
    if (this._editing) record.id = this._editing;
    if (record.invoice_balance !== null && record.correction !== null) { this._message("Podaj saldo z faktury albo korektę, nigdy oba naraz.", true); return; }
    const revision = this._editRevision ?? this._data?.revision;
    if (await this._run(() => this._call("put", { record, revision }, true), "Rozliczenie zapisane. Wyniki przeliczone.")) this._resetEditor();
  }

  async _delete(id) {
    if (confirm("Usunąć tę datę? Wszystkie zależne okresy i salda zostaną przeliczone.")) {
      if (await this._run(() => this._call("delete", { record_id: id }, true), "Rozliczenie usunięte.")) this._resetEditor();
    }
  }

  async _refresh(id) {
    if (confirm("Zastąpić zapisany odczyt nową próbką z Recorder? Wcześniej pobierz kopię JSON. Przeliczy to zależne okresy.")) await this._run(() => this._call("refresh_sample", { record_id: id }, true), "Odczyt zaktualizowany.");
  }

  async _diagnose() {
    await this._run(async () => {
      const result = await this._call("diagnose", { day: this.shadowRoot.getElementById("day").value });
      const box = this.shadowRoot.getElementById("diagnosis");
      box.hidden = false;
      box.textContent = JSON.stringify(result, null, 2);
    }, "Diagnostyka zakończona — wynik poniżej formularza.");
  }

  async _export() {
    await this._run(async () => {
      const document = await this._call("export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(document, null, 2)], { type: "application/json" }));
      const link = window.document.createElement("a");
      link.href = url;
      link.download = `magazyn-pge-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, "Utworzono plik kopii zapasowej.");
  }

  async _import(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !confirm("Zastąpić cały rejestr zawartością kopii JSON? Najpierw zachowaj bieżącą kopię.")) return;
    const revision = this._data?.revision;
    if (await this._run(async () => {
      const document = JSON.parse(await file.text());
      await this._call("import", { document, revision }, true);
    }, "Przywrócono kopię rejestru.")) this._resetEditor();
  }
}

if (!customElements.get("pge-storage-card")) customElements.define("pge-storage-card", PGEStorageCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "pge-storage-card")) window.customCards.push({ type: "pge-storage-card", name: "Magazyn energii PGE", description: "Saldo, historia faktur, wykres i edycja rozliczeń PGE" });
