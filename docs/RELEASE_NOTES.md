MagazynPGE 0.5.0 — osobne moduły i konfigurator energii.

- Osobne karty Lovelace: Energia w domu, Pojedynczy kafelek, Miesiące i dni, Projekcja magazynu i Konfigurator. Każda dostępna w GUI dodawania kart. Dotychczasowa `pge-storage-card` automatycznie pokazuje responsywny zestaw osobnych kart.
- Schemat PV, domu, sieci, lokalnego akumulatora i magazynu PGE. Przełącznik Teraz/Dzisiaj. Źródła wybierane z listy encji HA w oknie konfiguratora; bez restartu po zmianie. Moce dwukierunkowe +/− lub osobne kierunki, z wyborem znaku. Opcjonalnie do 16 odbiorców.
- 24 stałe sensory: zachowane dotychczasowe salda plus energie od faktury, moce, lokalny akumulator i dzisiejsze energie. Można używać ich w natywnych kafelkach, automatyzacjach i innych dashboardach. Oryginalne źródła pozostają nietknięte.
- Kompaktowe miesięczne rozliczenie z wykresem; kliknięcie miesiąca pokazuje tabelę dni i wykres. Wszystko z pozycji magazynu, po opuście. Kolumny: pobrano, oddano, stan magazynu, netto. Bez czasów i uwag przy każdym dniu.
- Trzy serie na wykresie: pobór rok wcześniej, pobór obecnie i projekcja magazynu. Osobna oś magazynu. Automatyczny odczyt statystyk, puste luki, bez przyszłych doładowań i zwiększania poboru.
- Faktury, usuwanie, edycja, kopie i partie energii w osobnym oknie. Rejestr i partie zachowane. URL modułu zawiera wersję i skrót zawartości; w konfiguratorze widać wersję integracji i karty.

Aktualizacja: HACS → 0.5.0 → restart HA → pełne odświeżenie przeglądarki (Ctrl+F5). Restart jest wymagany z powodu nowych sensorów, backendu i tras frontendowych. Nie usuwaj wpisu integracji ani faktur. Następnie Źródła energii → wybierz sensory → Zapisz źródła. Kolejne zmiany źródeł, faktur i planu działają bez restartu HA.
