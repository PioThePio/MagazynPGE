MagazynPGE 0.2.1 — poprawka ładowania karty w Home Assistant.

- Naprawiono błąd `Custom element doesn’t exist: pge-storage-card` w HA 2026.10.0 / frontendzie 20260930.2.
- Karta jest teraz modułem zasobów Lovelace, ładowanym po inicjalizacji frontendu. Integracja automatycznie dodaje i aktualizuje swój zasób w standardowym trybie HA.
- Dodano test w rzeczywistym Chromium, który otwiera dashboard HA, sprawdza wyświetlenie karty i ponownie ładuje stronę.

Aktualizacja: HACS → Magazyn energii PGE → Aktualizuj, następnie restart Home Assistant i odświeżenie przeglądarki Ctrl+F5. Zachowaj istniejący wpis integracji i konfigurację dashboardu. Rejestr faktur oraz format danych pozostają bez zmian.

Przy ręcznie ustawionym `lovelace.resource_mode: yaml` dodaj moduł `/pge_storage/pge-storage-card.js?v=0.2.1` do swoich zasobów; szczegóły w `docs/HACS.md`.

Wymagany Home Assistant Core 2026.10.0 lub nowszy. Testy korzystają z Core 2026.10.0 i frontendu 20260930.2.
