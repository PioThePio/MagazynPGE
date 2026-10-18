Wersja 0.7.0: 88 testów Python i 14 testów DOM. Rzeczywisty HA sprawdza stworzenie dashboardu z ośmioma kartami, zapis i zachowanie edycji, powtórne wywołanie, kolizję adresu, awarię zapisu i uprawnienia. Test importu odtwarza brakujący `sensor.solar_total_kwh` obok działającego MPPT: oba źródła pozostają w konfiguracji, zapis działa, historyczne sumy są odczytywane, a niepełna moc pozostaje nieznana. Sprawdzono też konwencje akumulatora i przemianowane sensory transformujące Energii. Chromium sprawdza szerokie okno 1440 px z kartą 500 px, telefon 390 px, brak przepełnień i nachodzenia wszystkich kół oraz podpisów, osobnych odbiorców, przycisk utworzenia i przejście do natywnego dashboardu. Obejrzano zrzuty nowego dashboardu desktop i mobile. DOM sprawdza listy PV, brakujące encje, usuwanie źródła bez utraty pozostałych statystyk, tryby mocy i zachowanie linku dashboardu przy aktualizacji danych.

Wersja 0.6.0: 82 testy Python i 12 testów DOM. Nowy test rzeczywistego HA zapisuje konfigurację natywnej Energii w izolowanym środowisku, importuje godzinowe sumy Wh z resetowanymi stanami i zewnętrzną statystyką, następnie sprawdza automatyczny import, bilans domu w W/kWh, oddzielenie liczników PGE, ręczne zastąpienie i przeładowanie. Testy jednostkowe obejmują wiele źródeł, brak danych, brak akumulatora/PV i zachowanie ręcznych wyborów. DOM sprawdza ponowny import z przycisku, listy wielu encji, zachowanie statystyk i opcję „Oblicz z bilansu”. Użytkownik bez uprawnień administratora nie może importować konfiguracji.

# Weryfikacja 2026-10-18

Wersja 0.5.0: **77 testów Python i 11 testów DOM zaliczonych**. Pełny frontend HA w Chromium sprawdza osobne moduły, kliknięcie miesiąca i dni, okno faktur, zaznaczanie tekstu, wybór źródła PV z listy i natychmiastową aktualizację bez restartu. Obejrzano zrzuty desktop 1440 px i telefon 430 px. Natywne testy Recorder sprawdzają różnice dzienne Wh→kWh, bilans miesięczny mimo usuniętych dni pośrednich, moce ze znakiem i ich kierunki, 24 encje, odbiorców, zachowanie konfiguracji po przeładowaniu i po zapisaniu faktury oraz brak mutacji źródeł przy błędnym zapisie. Importowane do izolowanej bazy kompletne statystyki godzinowe potwierdzają odczyt poprzedniego roku, bieżącego poboru i kompletną projekcję, z uwzględnieniem 745 godzin października ze zmianą czasu. Wykresy nie zamieniają braków na zero. Kopie wersji 2/3 bez nowych pól zachowują zgodność. Zasób ma wersję i skrót zawartości, a obie części frontendu są sprawdzane pod kątem składni.

Wersja 0.4.0: 70 testów Python i 10 testów DOM zaliczonych. Sprawdzono pięciokolumnowe dni pod rozwijanymi miesiącami, zaokrąglanie do pełnych kWh, trzykolumnową tabelę projekcji, propagację nieznanego salda po luce historii, nieuwzględnianie dowolnie dużego przyszłego eksportu, wygaśnięcia i datę rozliczenia 30 września → 31 marca. Historia importu działa również przy lukach eksportu. Źródłowy miesiąc spoza poprzedniego roku jest odrzucany w projekcji. Chromium sprawdza pełny dashboard, otwiera dni wybranego miesiąca i po zmianie poboru potwierdza datę wyczerpania zapasu. Ruff, składnia JS, metadane v0.4.0 i budowa archiwum przeszły kontrolę.

Wersja 0.3.0: sprawdzono dzienne importy/eksporty, wygaśnięcia i pobór pokryty magazynem, FIFO przy dodatnim bilansie netto, terminy włączne i lata przestępne, niepełny bieżący dzień ze zmianą czasu, brak danych bez zerowania, projekcje przyszłych liczników, niedobór zimowy i ochronę nieskończonych/ujemnych profili. Rzeczywisty HA sprawdza WS, zapis planu, odtworzenie starszego formatu, utrwalenie odczytów dziennych i miesięcznych po purgowaniu Recorder oraz odmowę zapisu dyskowego. Natywne API statystyk przetestowano na zaimportowanych w izolowanej bazie sumach Wh, z konwersją do kWh i różnicą 720/1440 kWh dla kompletnego miesiąca. Chromium otwiera tabelę dni i zmienia profil, po czym sprawdza nową prognozę niedoboru.

Wersja 0.2.2 nadpisuje odziedziczone `user-select: none` dashboardu. Test Chromium przeciąga mysz od początku do końca nagłówka oraz rzeczywistego komunikatu błędu braku historii i sprawdza tekst zaznaczenia. W oryginalnej karcie test zwracał puste zaznaczenie; po poprawce oba teksty można zaznaczyć.

Wersja 0.2.1 naprawia błąd `Custom element doesn’t exist: pge-storage-card` odtworzony w rzeczywistym Chromium z Core 2026.10.0 i frontendem 20260930.2. Globalny import JS wykonywał się przed inicjalizacją rejestru komponentów HA. Zastąpiono go modułem zasobów Lovelace. Nowy test otwiera dashboard bez ręcznego importowania JS, sprawdza treść karty, dostępność formularza i działanie po odświeżeniu strony. Sprawdzono również aktualizację starego URL, usunięcie duplikatu własnego zasobu, zachowanie innych zasobów oraz instrukcję dla trybu zasobów YAML.

Repozytorium i wydanie v0.2.0 zostały opublikowane na GitHubie. Zdalne workflow [Tests](https://github.com/PioThePio/MagazynPGE/actions/runs/39061961185) i [Release](https://github.com/PioThePio/MagazynPGE/actions/runs/39061979468) zakończyły się powodzeniem; pobrane publiczne archiwum v0.2.0 przeszło kontrolę CRC i zawartości. Workflow v0.2.1 instaluje dodatkowo Chromium i uruchamia test przeglądarkowy przed publikacją. Jego wynik jest dostępny w zakładce [Actions](https://github.com/PioThePio/MagazynPGE/actions).

Sprawdzono w odizolowanym środowisku chmurowym, bez dostępu do produkcyjnego HA użytkownika.

| Kontrola | Wynik |
|---|---|
| Python 3.14.8, Home Assistant Core 2026.10.0 | Zainstalowane i uruchomione |
| `uv sync --frozen`, `npm ci` | Wykonane, także ponownie bez zmian lockfile |
| pytest | 88 testów zaliczonych, 0 niezaliczonych, 0 pominiętych |
| Testy karty w DOM / Node 24 | 14 zaliczonych, 0 niezaliczonych |
| Chromium: pełny dashboard HA i ponowne ładowanie strony | Zaliczony (wśród 88 testów pytest) |
| Ruff check i format | Bez błędów |
| Składnia JS | Poprawna |
| `hass --script check_config -c .ha-dev` | Poprawna konfiguracja demonstracyjna |
| Serwer demonstracyjny | Frontend i API pierwszej konfiguracji odpowiadają HTTP 200 z oczekiwaną treścią |
| Powtórne przygotowanie `.ha-dev` | Zachowuje istniejącą konfigurację |

Testy rzeczywistego HA korzystają z osobnej SQLite Recorder, prawdziwego Config Flow, 24 encji i autoryzowanego HTTP/WebSocket. Weryfikują zapisane odczyty wstecz, wzory z przykładu, edycję i usuwanie, eksport/import, przetrwanie przeładowania, działanie otwartej subskrypcji po przeładowaniu, błędne daty, brak historii, konflikt równoczesnych edycji, odmowę zapisu dyskowego, opcje i odmowę operacji bez uprawnień. Obliczenia obejmują też ujemny bilans obliczony z nieujemnych liczników, saldo nieznane, wyzerowanie faktury, korektę, rozliczony niedobór, granice UTC, zmianę czasu i 500 dat.

Testy karty sprawdzają renderowanie, wyświetlanie ujemnych bilansów, wysyłanie zera z faktury, zachowanie niezapisanej edycji przy aktualizacjach, błędy serwera, paginację i traktowanie uwag jako tekstu. Osobny test Chromium sprawdza ładowanie karty przez pełny frontend HA. W wersji 0.5 obejrzano również układ przy szerokości 430 px.

Ostrzeżenia pytest pochodzą z zależności HA/aiohttp/backoff. W minimalnej demonstracyjnej instalacji HA może także logować brak opcjonalnej biblioteki `libturbojpeg` do przyspieszania obrazów kamer; magazyn energii jej nie używa. Obsługa kamer i pozostałych urządzeń HA nie należy do przygotowanego workflow.

Przypięto Core 2026.10.0 i frontend 20260930.2 do wersji podanych przez użytkownika. Nie zweryfikowano retencji, statystyk, fizycznego punktu pomiarowego ani częstotliwości próbkowania produkcyjnych liczników SDM640/Victron. Wymagają sprawdzenia w docelowym HA przyciskiem diagnostyki. Nie wdrożono zmian w produkcyjnym HA użytkownika; aktualizację pobiera on przez HACS. Publikacja kodu na GitHubie i testy izolowanego HA nie potwierdzają dostępności historii produkcyjnych liczników.

W wariancie 0.2 sprawdzono też konwersję Wh/kWh/MWh, jednokrotne zastosowanie współczynnika 0,8, oddzielne czasy dwóch próbek, walidację komponentów przy imporcie, spadki/reset licznika, przeliczenia po zmianie daty i ponownym odczycie oraz odmowę odczytu przy uprawnieniu tylko do jednego z dwóch źródeł.
