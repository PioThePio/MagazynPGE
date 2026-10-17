/* Magazyn PGE: self-contained Lovelace card; no external scripts or CDN. */
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
const fmt = (value) => value == null ? "—" : new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(Math.abs(Number(value)) < 0.5 ? 0 : Number(value));
const dayLabel = (day) => day ? day.split("-").reverse().join(".") : "—";
const stampLabel = (stamp) => new Date(stamp).toLocaleString("pl-PL", { timeZone: "Europe/Warsaw" });
const monthLabel = (month) => `${months[Number(month.slice(5)) - 1]} ${month.slice(0, 4)}`;
const months = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"];

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
  getGridOptions() { return { columns: "full", rows: "auto" }; }
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
        :host{display:block;-webkit-user-select:text;user-select:text}*{box-sizing:border-box}ha-card{padding:24px;color:var(--primary-text-color);overflow:hidden;max-width:1400px;margin:0 auto}
        h1{font-size:1.4rem;margin:0 0 8px}h2{font-size:1.1rem;margin:24px 0 12px}.muted{color:var(--secondary-text-color);font-size:.9rem;line-height:1.5}
        .metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin:20px 0}.metric{background:var(--secondary-background-color,#eee);border-radius:12px;padding:16px}.value{font-size:1.5rem;font-weight:600;margin-top:6px}
        .scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{padding:12px 10px;border-bottom:1px solid var(--divider-color,#ddd);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{font-weight:600}caption{text-align:left;margin:10px 0}
        button{background:var(--primary-color,#087f8c);color:var(--text-primary-color,#fff);border:0;border-radius:7px;padding:10px 14px;cursor:pointer;font:inherit}button.secondary{background:var(--secondary-background-color,#eee);color:var(--primary-text-color)}button.danger{background:#a42828;color:white}button:disabled{opacity:.5;cursor:wait}
        .tools{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:14px 0}.notice{border-left:4px solid var(--primary-color,#087f8c);padding:12px;margin:12px 0;background:var(--secondary-background-color,#eee)}.error{border-left-color:#b3261e} .notice:empty{display:none}
        summary{cursor:pointer;font-weight:600;padding:12px 0}details{margin-top:12px}.hero{font-size:2.2rem;font-weight:700}.compact th,.compact td{padding:9px 6px;white-space:normal}.compact input{width:100%;min-width:75px;padding:7px}.compact small{display:block}select{font:inherit;max-width:100%;padding:10px}#lots{min-height:140px}#flow{line-height:1.7}.month-block{border:1px solid var(--divider-color,#ddd);border-radius:12px;padding:0 14px;margin:10px 0}.month-block>summary{display:flex;justify-content:space-between;gap:12px;align-items:center;list-style:none}.month-block>summary::before{content:"▸";color:var(--primary-color,#087f8c)}.month-block[open]>summary::before{content:"▾"}.month-block>summary .month-name{flex:1}.month-totals{font-size:.85rem;font-weight:400;color:var(--secondary-text-color)}.in{color:var(--primary-color,#087f8c)}.out{color:#b55235}.balance{font-weight:600}.month-block table{margin-bottom:12px}.month-block small{display:block}.month-block .tools{justify-content:space-between}#forecast-table td small{display:block;color:var(--secondary-text-color);font-size:.75rem} @media(max-width:600px){ha-card{padding:16px}.month-block{padding:0 8px}.month-block>summary{flex-wrap:wrap}.month-totals{flex-basis:100%;padding-left:22px}.compact th,.compact td{padding:10px 4px;font-size:.78rem}}.scroll{overscroll-behavior-x:contain}#daily-note{margin-top:8px}#plan-summary{white-space:pre-line}
        form{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}label{display:flex;flex-direction:column;gap:7px;font-size:.9rem}input,textarea{font:inherit;padding:10px;border-radius:6px;border:1px solid var(--divider-color,#aaa);background:var(--card-background-color,#fff);color:var(--primary-text-color)}textarea{resize:vertical}.full{grid-column:1/-1}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.8rem}.chart{min-width:480px}.chart svg{display:block;width:100%;max-height:260px}.chart text{fill:var(--secondary-text-color,#555);font-size:11px}.positive{fill:var(--primary-color,#087f8c)}.negative{fill:#b55235}[hidden]{display:none!important}
      </style>
      <ha-card>
        <h1>${esc(this._config.title || "Wirtualny magazyn PGE")}</h1>
        <div class="muted">MAGAZYN = energia do odbioru po opuście 20%. Wprowadzona przed opustem = MAGAZYN ÷ 0,8. Granice dni: Europe/Warsaw.</div>
        <div id="message" class="notice" role="status" aria-live="polite"></div>
        <div id="metrics" class="metrics"></div>
        <div id="period" class="muted">Łączenie z rejestrem…</div>
        <div id="warnings" class="notice"></div>
        <div id="flow" class="notice"></div>
        <h2>Wpłaty i pobory</h2>
        <p class="muted">Wszystkie wartości w kWh do odbioru. Wprowadzono: po odjęciu 20%. Kliknij miesiąc, aby zobaczyć dni.</p>
        <div id="daily-months"></div>
        <div class="tools"><label>Inny miesiąc<input id="daily-month" type="month"></label><button id="daily-refresh" class="secondary">Pokaż miesiąc</button></div>
        <h2>Obecny magazyn do następnego rozliczenia</h2>
        <div id="plan-summary" class="notice"></div>
        <div id="forecast-table" class="scroll"></div>
        <div id="expiry-table"></div>
        <details id="plan-settings" data-admin><summary>Ustaw datę rozliczenia, historię poboru i partie</summary>
          <form id="plan-editor">
            <label>Następne rozliczenie<input id="target-day" type="date" required></label>
            <label>Faktura odniesienia<select id="plan-anchor"></select></label>
            <label class="full">Partie z faktury: miesiąc; pozostały eksport przed opustem [kWh]; ważne do<textarea id="lots" placeholder="RRRR-MM; kWh; RRRR-MM-DD"></textarea></label>
            <div class="muted full">Suma partii × 0,8 musi odpowiadać saldu faktury. Pusty termin oznacza regułę 12 miesięcy od końca miesiąca wprowadzenia. Daty możesz zmienić zgodnie z zasadami swojego rozliczenia. Pobór zużywa najstarsze partie. To miesięczny model FIFO, nie potwierdzenie salda operatora.</div>
            <div class="tools full"><button id="lots-import" type="button" class="secondary">Wczytaj partie z pliku</button><input id="lots-file" type="file" accept=".json,application/json" hidden></div>
            <div class="full"><h2>Pobór z sieci w poprzednim roku [kWh]</h2><p class="muted">To podstawa tabeli powyżej: ile pobrano z sieci w tym samym miesiącu rok wcześniej. Nie dodajemy przyszłego eksportu. Puste pole oznacza brak danych, a nie zero. Wartości można uzupełnić z historii lub wpisać ręcznie. Bieżący miesiąc liczymy tylko od teraz, proporcjonalnie do pozostałego czasu.</p>
              <button id="profile-load" type="button" class="secondary">Wczytaj pobór z historii HA</button><div id="profile-note" class="muted"></div>
              <table class="compact"><thead><tr><th>Miesiąc</th><th>Pobrano w całym miesiącu [kWh]</th><th>Źródło</th></tr></thead><tbody>${months.map((name, index) => `<tr><td>${name}</td><td><input aria-label="${name}: pobór" data-profile="import" data-month="${index + 1}" type="number" min="0" step="any"></td><td data-profile-basis="${index + 1}">Brak historii</td></tr>`).join("")}</tbody></table>
            </div>
            <div class="tools full"><button type="submit">Zapisz plan i przelicz prognozę</button><button id="plan-refresh" type="button" class="secondary">Odśwież historię partii</button></div>
          </form>
        </details>
        <h2>Historia rozliczeń</h2>
        <div class="muted">Pierwsza data to punkt początkowy. Bilans okresu obejmuje energię po poprzedniej dacie, do końca kolejnej daty włącznie.</div>
        <div class="scroll"><table><caption>Wszystkie wartości energii w kWh. Znak minus oznacza niedobór.</caption>
          <thead><tr><th>Koniec dnia</th><th>Saldo z faktury</th><th>Bilans okresu</th><th>Saldo przeniesione</th><th>Szczegóły</th><th data-admin>Akcje</th></tr></thead>
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
    root.getElementById("daily-month").value = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw", year: "numeric", month: "2-digit" }).format(new Date());
    root.getElementById("daily-month").onchange = () => this._loadDaily();
    root.getElementById("daily-refresh").onclick = () => this._loadDaily();
    root.getElementById("plan-editor").onsubmit = (event) => { event.preventDefault(); this._savePlan(); };
    root.getElementById("plan-editor").oninput = (event) => {
      this._planDirty = true; this._planRevision ??= this._data?.revision;
      if (event.target.dataset.profile) {
        event.target.dataset.sourceMonth = "";
        root.querySelector(`[data-profile-basis="${event.target.dataset.month}"]`).textContent = "Wpisano ręcznie";
      }
    };
    root.getElementById("profile-load").onclick = () => this._loadProfile();
    root.getElementById("plan-refresh").onclick = () => this._run(() => this._call("refresh_plan"), "Historia partii odświeżona.");
    root.getElementById("lots-import").onclick = () => root.getElementById("lots-file").click();
    root.getElementById("lots-file").onchange = (event) => this._loadLots(event);
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
    const fields = [["available_energy", "MAGAZYN — do odbioru"], ["raw_export_remaining", "Wprowadzona — przed opustem"], ["deficit", "Niedobór"], ["carried_balance", "Po ostatniej fakturze"], ["period_balance", "Zmiana od faktury"]];
    const inventoryBalance = this._data.planning?.inventory?.balance_kwh;
    root.getElementById("metrics").innerHTML = fields.map(([key, title]) => {
      const available = inventoryBalance != null ? Math.max(0, Number(inventoryBalance)) : current.available_energy;
      const value = key === "raw_export_remaining" ? available == null ? null : Number(available) / 0.8 : key === "available_energy" ? available : inventoryBalance != null && key === "deficit" ? Math.max(0, -Number(inventoryBalance)) : current[key];
      return `<div class="metric"><div>${title}</div><div class="value">${fmt(value)} <small>kWh</small></div></div>`;
    }).join("");
    root.getElementById("flow").textContent = current.import_since_settlement_kwh != null ? `Od ${dayLabel(current.start_day)}: pobrano ${fmt(current.import_since_settlement_kwh)} kWh; oddano ${fmt(current.export_since_settlement_kwh)} kWh → dodano ${fmt(current.credited_since_settlement_kwh)} kWh po opuście. Zmiana netto: ${fmt(current.period_balance)} kWh.` : "Przepływy od faktury pojawią się po dodaniu punktu początkowego.";
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
      <td>${fmt(row.invoice_balance)}</td><td>${fmt(row.period_balance)}</td><td>${fmt(row.carried_balance)}</td>
      <td><details><summary>Pokaż</summary>Import: ${fmt(row.sample.components?.import?.value)} kWh (${esc(stampLabel(row.sample.components?.import?.recorded_at || row.sample.recorded_at))})<br>Eksport: ${fmt(row.sample.components?.export?.value)} kWh (${esc(stampLabel(row.sample.components?.export?.recorded_at || row.sample.recorded_at))})<br>Bilans liczników: ${fmt(row.sample.value)} kWh<br>Szacunek przed fakturą: ${fmt(row.estimated_before_invoice)} kWh<br>Różnica faktura − HA: ${fmt(row.invoice_difference)} kWh<br>Korekta: ${fmt(row.correction)} kWh<br>Niedobór z faktury: ${fmt(row.invoice_shortfall)} kWh<br>${esc(row.note)}</details></td>
      <td data-admin><button class="secondary" data-action="edit" data-id="${esc(row.id)}">Edytuj</button> <button class="secondary" data-action="refresh" data-id="${esc(row.id)}">Odczytaj ponownie</button> <button class="danger" data-action="delete" data-id="${esc(row.id)}">Usuń</button></td>
      </tr>`).join("") || '<tr><td colspan="13">Brak zapisanych dat.</td></tr>';
    root.getElementById("chart").innerHTML = this._chart(records.filter((r) => r.period_balance != null).slice(-12));
    this._renderMonths();
    this._renderPlanning();
    this._adminVisibility();
  }

  _chart(rows) {
    if (!rows.length) return '<p class="muted">Wykres pojawi się po dodaniu co najmniej dwóch dat.</p>';
    const width = Math.max(600, rows.length * 95);
    const scale = 75 / Math.max(1, ...rows.map((r) => Math.abs(Number(r.period_balance))));
    return `<svg viewBox="0 0 ${width} 245" role="img" aria-label="Porównanie bilansów zamkniętych okresów w kWh"><line x1="0" y1="115" x2="${width}" y2="115" stroke="currentColor" opacity=".4"/>${rows.map((row, index) => {
      const value = Number(row.period_balance), height = Math.abs(value) * scale;
      const center = (index + 0.5) * width / rows.length;
      return `<g><title>Po ${esc(row.start_day)} do ${esc(row.day)}: ${esc(fmt(row.period_balance))} kWh</title><rect class="${value >= 0 ? "positive" : "negative"}" x="${center - 23}" y="${value >= 0 ? 115 - height : 115}" width="46" height="${Math.max(1, height)}" rx="3"/><text x="${center}" y="${value >= 0 ? 105 - height : 132 + height}" text-anchor="middle">${esc(fmt(row.period_balance))}</text><text x="${center}" y="225" text-anchor="middle">${esc(dayLabel(row.day))}</text></g>`;
    }).join("")}</svg>`;
  }

  _monthBlock(month) {
    const root = this.shadowRoot;
    let block = root.querySelector(`[data-daily-month="${month}"]`);
    if (block) return block;
    block = window.document.createElement("details");
    block.className = "month-block";
    block.dataset.dailyMonth = month;
    block.innerHTML = `<summary><span class="month-name">${esc(monthLabel(month))}</span><span class="month-totals">Pokaż dni</span></summary><div class="tools"><span class="muted" data-daily-note></span><button class="secondary" data-day-refresh>Odśwież</button></div><div class="scroll"><table class="compact"><thead><tr><th>Data</th><th>Wprowadzono</th><th>Pobrano</th><th>Różnica</th><th>Saldo na koniec dnia</th></tr></thead><tbody data-daily-rows></tbody></table></div>`;
    block.ontoggle = () => { if (block.open && !block.dataset.loaded && !block.dataset.loading) this._loadDaily(month); };
    block.querySelector("[data-day-refresh]").onclick = () => this._loadDaily(month);
    const next = [...root.getElementById("daily-months").children].find((item) => item.dataset.dailyMonth < month);
    root.getElementById("daily-months").insertBefore(block, next || null);
    return block;
  }

  _renderMonths() {
    const key = `${this._data.entry_id}:${this._data.revision}`;
    if (this._monthsKey !== key) { this.shadowRoot.getElementById("daily-months").replaceChildren(); this._monthsKey = key; }
    const today = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw", year: "numeric", month: "2-digit" }).format(new Date());
    const first = this._data.records[0]?.day.slice(0, 7) || today;
    // Show a year at a time; older months are available with the month picker.
    let [year, month] = today.split("-").map(Number);
    for (let index = 0; index < 12; index++) {
      const key = `${year}-${String(month).padStart(2, "0")}`;
      if (key < first) break;
      this._monthBlock(key);
      if (--month === 0) { month = 12; year--; }
    }
  }

  async _loadDaily(month = this.shadowRoot.getElementById("daily-month").value) {
    if (!/^\d{4}-\d{2}$/.test(month)) return;
    const block = this._monthBlock(month);
    block.open = true;
    const request = block._request = (block._request || 0) + 1;
    block.dataset.loading = "true";
    const note = block.querySelector("[data-daily-note]");
    note.textContent = "Wczytywanie…";
    try {
      const result = await this._call("daily", { month });
      if (request !== block._request || !result) return;
      block.querySelector("[data-daily-rows]").innerHTML = result.rows.map((row) => `<tr>
        <td>${esc(dayLabel(row.day))}${row.partial ? "<small>dzisiaj, do teraz</small>" : ""}${row.invoice ? "<small>rozliczenie</small>" : ""}${row.error ? `<small class="muted" title="${esc(row.error)}">Brak historii</small>` : ""}${Number(row.expired_kwh) > 0 ? `<small>Wygasło: ${fmt(row.expired_kwh)} kWh</small>` : ""}</td>
        <td class="in">${fmt(row.credited_kwh)}</td><td class="out">${fmt(row.import_kwh)}</td><td>${fmt(row.net_kwh)}</td><td class="balance">${fmt(row.balance_kwh)}</td></tr>`).join("");
      const sum = (field) => result.rows.length && result.rows.every((row) => row[field] != null) ? result.rows.reduce((total, row) => total + Number(row[field]), 0) : null;
      const last = result.rows.at(-1);
      block.querySelector(".month-totals").textContent = `+ ${fmt(sum("credited_kwh"))} / − ${fmt(sum("import_kwh"))} · różnica ${fmt(sum("net_kwh"))} · saldo ${fmt(last?.balance_kwh)} kWh`;
      note.textContent = `Stan na ${stampLabel(result.updated_at)}. Saldo uwzględnia rozliczenia i znane wygaśnięcia.`;
      block.dataset.loaded = "true";
    } catch (error) {
      if (request !== block._request) return;
      note.textContent = error.message || String(error);
    } finally { if (request === block._request) delete block.dataset.loading; }
  }

  _renderPlanning() {
    const root = this.shadowRoot, plan = this._data.planning;
    if (!plan) { root.getElementById("plan-summary").textContent = "Prognoza i terminy wymagają aktualnej integracji."; return; }
    const forecast = plan.forecast, inventory = plan.inventory;
    const lines = [];
    if (plan.error) lines.push(plan.error);
    lines.push(`Do ${dayLabel(plan.target_day)}. Odejmujemy pobór taki jak rok wcześniej, bez przyszłych doładowań i bez zwiększania zużycia. Uwzględniamy znane terminy ważności.`);
    if (plan.inventory_error) lines.push(plan.inventory_error);
    if (plan.missing_profile_months?.length) lines.push(`Brak historii poboru: ${plan.missing_profile_months.map((month) => months[month - 1]).join(", ")}. Użyj „Wczytaj pobór z historii HA” w ustawieniach. Saldo od pierwszej luki pozostaje nieznane.`);
    if (forecast?.complete) lines.push(`Saldo na rozliczenie: ${fmt(forecast.balance_kwh)} kWh.${forecast.first_shortfall_day ? ` Zapas wyczerpie się: ${dayLabel(forecast.first_shortfall_day)}.` : " Zapas wystarcza do rozliczenia."}`);
    root.getElementById("plan-summary").textContent = lines.join("\n");
    root.getElementById("expiry-table").innerHTML = inventory ? `<details><summary>Terminy wykorzystania pozostałych partii</summary><div class="scroll"><table class="compact"><thead><tr><th>Wprowadzono</th><th>Przed opustem [kWh]</th><th>Do odbioru [kWh]</th><th>Ważne do</th></tr></thead><tbody>${inventory.lots.map((item) => `<tr><td>${esc(item.month)}</td><td>${fmt(Number(item.kwh) / 0.8)}</td><td>${fmt(item.kwh)}</td><td>${esc(dayLabel(item.expires_on))}</td></tr>`).join("")}</tbody></table></div></details>` : "";
    root.getElementById("forecast-table").innerHTML = forecast ? `<table class="compact"><thead><tr><th>Miesiąc</th><th>Prognozowany pobór [kWh]</th><th>Saldo po poborze [kWh]</th></tr></thead><tbody>${forecast.rows.map((row, index) => {
      const expired = row.expired_kwh == null ? null : Number(row.expired_kwh) - Number(index ? forecast.rows[index - 1].expired_kwh || 0 : inventory?.expired_kwh || 0);
      return `<tr><td>${esc(monthLabel(row.day.slice(0, 7)))}<small>do ${esc(dayLabel(row.day))}${index === 0 ? ", od teraz" : ""}</small></td><td>${row.period_import_kwh == null ? "Brak historii" : fmt(row.period_import_kwh)}<small>${esc(row.source_month ? `Historia: ${row.source_month}` : row.period_import_kwh != null ? "Zapisana wartość" : `Potrzebny ${row.expected_source_month}`)}</small></td><td class="balance">${fmt(row.balance_kwh)}${expired > 0 ? `<small>W tym wygaśnięcie: ${fmt(expired)} kWh</small>` : ""}</td></tr>`;
    }).join("")}</tbody></table>` : "";
    if (!this._planDirty) {
      root.getElementById("plan-anchor").innerHTML = '<option value="">Wybierz fakturę</option>' + this._data.records.slice(-1).filter((row) => row.invoice_balance != null).map((row) => `<option value="${esc(row.id)}">${esc(dayLabel(row.day))}: ${fmt(row.invoice_balance)} kWh</option>`).join("");
      root.getElementById("plan-anchor").value = plan.config.anchor_id || "";
      root.getElementById("target-day").value = plan.target_day;
      root.getElementById("lots").value = plan.config.lots.map((lot) => `${lot.month}; ${lot.export_kwh}; ${lot.expires_on}`).join("\n");
      for (const input of root.querySelectorAll("[data-profile]")) {
        const item = plan.config.profile.find((item) => item.month === Number(input.dataset.month));
        input.value = item?.import_kwh ?? "";
        input.dataset.sourceMonth = item?.source_month || "";
        root.querySelector(`[data-profile-basis="${input.dataset.month}"]`).textContent = item ? item.source_month || "Zapisana wartość" : "Brak historii";
      }
      this._planRevision = null;
    }
  }

  async _savePlan() {
    const root = this.shadowRoot;
    const success = await this._run(async () => {
      const lots = root.getElementById("lots").value.split("\n").filter((line) => line.trim()).map((line) => {
        const parts = line.split(";").map((s) => s.trim());
        if (parts.length < 2 || parts.length > 3 || !/^\d{4}-\d{2}$/.test(parts[0]) || !parts[1]) throw new Error("Partie wpisz jako: RRRR-MM; kWh; RRRR-MM-DD.");
        const [year, month] = parts[0].split("-").map(Number);
        return { month: parts[0], export_kwh: parts[1].replace(",", "."), expires_on: parts[2] || new Date(Date.UTC(year + 1, month, 0)).toISOString().slice(0, 10) };
      });
      const profile = [];
      for (let month = 1; month <= 12; month++) {
        const imported = root.querySelector(`[data-profile="import"][data-month="${month}"]`).value;
        if (!imported) continue;
        const input = root.querySelector(`[data-profile="import"][data-month="${month}"]`);
        profile.push({ month, import_kwh: imported, export_kwh: "0", ...(input.dataset.sourceMonth ? { source_month: input.dataset.sourceMonth } : {}) });
      }
      await this._call("put_plan", { planning: { anchor_id: root.getElementById("plan-anchor").value || null, lots, profile, target_day: root.getElementById("target-day").value }, revision: this._planRevision ?? this._data.revision }, true);
    }, "Plan zapisany. Prognoza przeliczona.");
    if (success) { this._planDirty = false; this._planRevision = null; this._renderPlanning(); }
  }

  async _loadProfile() {
    await this._run(async () => {
      const result = await this._call("profile");
      this._planRevision ??= this._data.revision;
      this._planDirty = true;
      for (const input of this.shadowRoot.querySelectorAll("[data-profile]")) {
        const item = result.profile.find((item) => item.month === Number(input.dataset.month));
        input.value = item?.import_kwh ?? "";
        input.dataset.sourceMonth = item?.source_month || "";
        this.shadowRoot.querySelector(`[data-profile-basis="${input.dataset.month}"]`).textContent = item?.source_month || "Brak historii";
      }
      this.shadowRoot.getElementById("profile-note").textContent = `Wczytano: ${Object.values(result.basis).join(", ") || "brak pełnych miesięcy"}. Brakujące miesiące: ${result.missing.map((month) => months[month - 1]).join(", ") || "brak"}. HA nie ma dla nich kompletnych statystyk poboru. ${result.note} Sprawdź i zapisz.`;
    }, "Wczytano dostępny profil. Sprawdź założenia i zapisz plan.");
  }

  async _loadLots(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    await this._run(async () => {
      const data = JSON.parse(await file.text());
      if (!Array.isArray(data.lots) || data.lots.length > 120) throw new Error("Nieprawidłowy plik partii.");
      const anchor = this._data.records.find((row) => row.day === data.anchor_day);
      if (!anchor) throw new Error("Najpierw dodaj rozliczenie dla daty zapisanej w pliku partii.");
      this._planRevision ??= this._data.revision;
      this._planDirty = true;
      this.shadowRoot.getElementById("plan-anchor").value = anchor.id;
      this.shadowRoot.getElementById("lots").value = data.lots.map((lot) => `${lot.month}; ${lot.export_kwh}; ${lot.expires_on}`).join("\n");
    }, "Partie wczytane do formularza. Sprawdź daty i zapisz plan.");
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
