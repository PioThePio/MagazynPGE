# Weryfikacja 2026-10-17

Obsługa HACS: dodano `hacs.json`, ikonę `brand/icon.png`, instrukcję instalacji oraz workflow **Release** uruchamiany tagiem. Lokalnie zweryfikowano spójność wersji `v0.2.0`, odrzucenie błędnego taga, składnię YAML workflow, obecność ikony i karty w paczce. Po tych zmianach nadal przeszło 46 testów Python i 6 testów karty. Nie wykonano zdalnego workflow ani instalacji przez HACS: w chwili sprawdzania GitHub nie zwracał publicznej strony repozytorium (HTTP 404), a repozytorium nie zgłaszało zdalnych referencji. Publikacja kodu i pierwszego publicznego wydania pozostaje osobnym krokiem.

Sprawdzono w odizolowanym środowisku chmurowym, bez dostępu do produkcyjnego HA użytkownika.

| Kontrola | Wynik |
|---|---|
| Python 3.14.8, Home Assistant Core 2026.10.0 | Zainstalowane i uruchomione |
| `uv sync --frozen`, `npm ci` | Wykonane, także ponownie bez zmian lockfile |
| pytest | 46 testów zaliczonych, 0 niezaliczonych, 0 pominiętych |
| Testy karty w DOM / Node 24 | 6 zaliczonych, 0 niezaliczonych |
| Ruff check i format | Bez błędów |
| Składnia JS | Poprawna |
| `hass --script check_config -c .ha-dev` | Poprawna konfiguracja demonstracyjna |
| Serwer demonstracyjny | Frontend i API pierwszej konfiguracji odpowiadają HTTP 200 z oczekiwaną treścią |
| Powtórne przygotowanie `.ha-dev` | Zachowuje istniejącą konfigurację |

Testy rzeczywistego HA korzystają z osobnej SQLite Recorder, prawdziwego Config Flow, pięciu encji i autoryzowanego HTTP/WebSocket. Weryfikują zapisane odczyty wstecz, wzory z przykładu, edycję i usuwanie, eksport/import, przetrwanie przeładowania, działanie otwartej subskrypcji po przeładowaniu, błędne daty, brak historii, konflikt równoczesnych edycji, odmowę zapisu dyskowego, opcje i odmowę operacji bez uprawnień. Obliczenia obejmują też ujemny bilans obliczony z nieujemnych liczników, saldo nieznane, wyzerowanie faktury, korektę, rozliczony niedobór, granice UTC, zmianę czasu i 500 dat.

Testy karty sprawdzają renderowanie, wyświetlanie ujemnych bilansów, wysyłanie zera z faktury, zachowanie niezapisanej edycji przy aktualizacjach, błędy serwera, paginację i traktowanie uwag jako tekstu. To testy DOM, nie pełny test przeglądarkowy ani ocena wyglądu na telefonie.

Ostrzeżenia pytest pochodzą z zależności HA/aiohttp/backoff. W minimalnej demonstracyjnej instalacji HA może także logować brak opcjonalnej biblioteki `libturbojpeg` do przyspieszania obrazów kamer; magazyn energii jej nie używa. Obsługa kamer i pozostałych urządzeń HA nie należy do przygotowanego workflow.

Przypięto Core 2026.10.0 i frontend 20260930.2 do wersji podanych przez użytkownika. Nie zweryfikowano retencji, statystyk, fizycznego punktu pomiarowego ani częstotliwości próbkowania produkcyjnych liczników SDM640/Victron. Wymagają sprawdzenia w docelowym HA przyciskiem diagnostyki. Nie przeprowadzono publikacji środowiska ani wdrożenia w HA użytkownika. Konfiguracja CI jest dodana do repozytorium; wykonano jej lokalne polecenia, nie zdalny workflow GitHub Actions.

W wariancie 0.2 sprawdzono też konwersję Wh/kWh/MWh, jednokrotne zastosowanie współczynnika 0,8, oddzielne czasy dwóch próbek, walidację komponentów przy imporcie, spadki/reset licznika, przeliczenia po zmianie daty i ponownym odczycie oraz odmowę odczytu przy uprawnieniu tylko do jednego z dwóch źródeł.
