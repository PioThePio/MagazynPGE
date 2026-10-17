MagazynPGE 0.2.2 — zaznaczanie i kopiowanie tekstu na karcie.

- Przywrócono zaznaczanie tekstu myszą na karcie: komunikatów błędów, odczytów, tabeli i diagnostyki. Karta nadpisuje blokadę zaznaczania odziedziczoną z dashboardu Home Assistant.
- Test rzeczywistego dashboardu w Chromium sprawdza teraz zaznaczenie nagłówka i błędu braku historii przez przeciągnięcie myszą. Przed poprawką zaznaczenie było puste.

Aktualizacja: HACS → Magazyn energii PGE → Aktualizuj do 0.2.2, restart Home Assistant i odświeżenie strony Ctrl+F5. Konfiguracja integracji, dashboard i zapisane rozliczenia pozostają zachowane.

Przy ręcznie zarządzanych zasobach YAML zaktualizuj URL modułu do `/pge_storage/pge-storage-card.js?v=0.2.2`.

Ta poprawka dotyczy zaznaczania tekstu. Komunikat braku historycznej próbki oznacza brak odczytu w wybranym oknie Recorder; nie potwierdza sam w sobie usunięcia całej historii.
