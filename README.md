# Magazyn energii PGE dla Home Assistant

Wirtualny magazyn energii z historią faktur i kartą Lovelace. Wersja 0.2 odczytuje **dwa oddzielne liczniki energii sieciowej** i samodzielnie oblicza `eksport × 0,8 − import`. Gotowy sensor bilansu `export-import` nie jest źródłem. Wszystkie istniejące sensory, ich historia i statystyki pozostają tylko do odczytu.

To integracja lokalna: bez konta PGE, bez chmury zewnętrznej, bez Pyscript, AppDaemon, MQTT i dodatkowej bazy danych. Nie pobiera faktur z PGE.

## Źródła w Twojej instalacji

| Zestaw | Import z sieci | Eksport do sieci |
|---|---|---|
| SDM640 — podstawowy wybór | „630 E import”, kWh | „630 E export”, kWh |
| Victron — alternatywna para | `energymeter_consumption`, kWh | `energymeter_feed_in`, kWh |

Wybierz **jedną pełną parę** w GUI. Nie dodajemy wskazań SDM640 do Victrona: mierzą ten sam przepływ energii. Integracja nie zgaduje `entity_id` z nazwy wyświetlanej. Wybierając Victrona, wskaż rzeczywiste encje z listy HA odpowiadające podanym nazwom. Nie zakładaj automatycznie prefiksu ani konkretnej pisowni identyfikatora.

Oba liczniki muszą obejmować ten sam punkt przyłączenia do sieci, mieć narastające wartości i nie resetować się w analizowanym zakresie. Nie wybieraj energii ładowania/rozładowania baterii, mocy W/kW, SOC ani dziennych liczników energii. Nie przełączamy źródła automatycznie w razie braku danych — różne liczniki mogą mieć inne początki naliczania i historię.

## Dlaczego mała integracja

Natywne szablony dobrze wyliczają różnice, ale nie zarządzają trwałą, edytowalną listą dowolnej długości ani historycznymi odczytami Recorder. `utility_meter` nadaje się do cykli i taryf, ale nie zapewnia tego rejestru zmiennych dat, faktur i korekt. Helper dla każdego okresu oznaczałby rozrastającą się ręczną konfigurację.

Rozwiązanie składa się z jednego wpisu integracji, jednego pliku danych HA, pięciu sensorów wynikowych i jednej karty z formularzem, tabelą oraz wykresem. Nie powstają nowe encje dla kolejnych faktur. Szczegóły i źródła API: [architektura](docs/ARCHITEKTURA.md).

## Zgodność i ograniczenia

- **Przetestowana wersja: Home Assistant Core 2026.10.0, Python 3.14.8.** Środowisko deweloperskie jest przypięte do tej wersji. Ta wersja HA wymaga Python ≥3.14.2.
- Wskazana instalacja to **HA OS 18.3, Core 2026.10.0, Supervisor 2026.10.2, frontend 20260930.2**. Testy uruchomiono na tym samym Core i frontendzie. Supervisor i HA OS zarządzają Twoim urządzeniem; nie instalujemy ich w chmurze. Dla zgodności integracji istotny jest Core, nie numer Supervisora.
- Każdy licznik musi mieć nieujemny liczbowy stan w **Wh, kWh lub MWh**; odczyty przeliczamy do kWh. Obliczony bilans i bilanse okresów mogą być dodatnie albo ujemne. Spadek licznika pomiędzy granicami jest błędem ciągłości. Resetu ukrytego pomiędzy próbkami nie da się wykryć wyłącznie z odczytów granicznych, dlatego wymagamy liczników bez resetów.
- Odtwarzamy **ostatni zapisany stan**, nie dokładną fizyczną wartość w chwili północy. Czas każdej z dwóch próbek jest widoczny; liczniki nie muszą aktualizować się jednocześnie. Dokładność zależy od częstotliwości źródła i ciągłości rejestracji.
- Gdy Recorder usunął wymagane dane, integracja odmawia utworzenia odczytu. Statystyki długoterminowe nie przywrócą dokładnej wartości końcowej. Nie ma interpolacji ani wpisywania zmyślonych wartości.
- Wygaśnięcia energii, roczniki, FIFO i planowanie zużycia pozostają etapem drugim. Dzisiejsze saldo jest szacunkiem opartym na Twoich fakturach i pomiarze, bez automatycznego modelowania regulaminu PGE.

## Instalacja w Twoim HA

**Zalecane: [instalacja i aktualizacje przez HACS](docs/HACS.md).** Raz dodajesz publiczne repozytorium jako integrację, a potem klikasz aktualizację i restartujesz HA. Karta Lovelace aktualizuje się razem z integracją. HACS wymaga wcześniejszego opublikowania kodu oraz wydania na GitHubie — lokalny ZIP nie jest jeszcze repozytorium dostępnym w HACS. Instrukcja dla autora: [publikowanie wydań](docs/WYDANIA.md).

Poniżej pozostaje alternatywna instalacja ręczna:

1. Zrób pełną kopię zapasową HA. W **Narzędzia deweloperskie → Stany** znajdź oddzielne liczniki „630 E import” i „630 E export” albo odpowiadającą im parę Victrona z tabeli powyżej. Sprawdź kierunki przepływu, jednostki oraz narastający charakter bez resetów. Nie wybieraj sensora gotowego bilansu.
2. Skopiuj katalog [custom_components/pge_storage](custom_components/pge_storage) do katalogu konfiguracji HA, aby powstał `/config/custom_components/pge_storage/manifest.json`. Kopiuj tylko integrację, bez `.venv`, `node_modules`, testów i środowiska `.ha-dev`. Zachowaj inne własne integracje.
3. Uruchom ponownie HA. Standardowe ostrzeżenie HA o nieoficjalnej integracji jest spodziewane.
4. **Ustawienia → Urządzenia i usługi → Dodaj integrację → Magazyn energii PGE**. Wybierz osobno import oraz eksport z tej samej pary pomiarowej. Domyślny maksymalny wiek każdej próbki to 24 godziny; można zmienić go w opcjach integracji (1–168 h). Większa wartość oznacza zgodę na starszy odczyt, a nie odzyskanie utraconej historii.
5. Utwórz dedykowany pusty dashboard, przejmij jego ręczną edycję i w edytorze surowej konfiguracji wklej [dashboards/pge.yaml](dashboards/pge.yaml). Możesz też dodać pojedynczą kartę ręcznie:

   ```yaml
   type: custom:pge-storage-card
   title: Wirtualny magazyn PGE
   ```

   Skrypt karty integracja udostępnia i rejestruje automatycznie. W standardowym trybie zasobów HA dodaje moduł do zasobów Lovelace; nie wymaga osobnego dodatku z HACS. Przy `lovelace.resource_mode: yaml` dodaj zasób zgodnie z [instrukcją HACS](docs/HACS.md). Jeśli karta nie pojawia się po instalacji, odśwież przeglądarkę. Przy kilku wpisach integracji ustaw na karcie `entry_id` odczytany z adresu strony danego wpisu w ustawieniach HA.
6. Jako administrator wpisz datę i kliknij **Sprawdź historię dla daty**. Wynik pokazuje filtr Recorder, obecność metadanych statystyk i oba znalezione odczyty i ich czasy albo nazwę kierunku, dla którego brakuje danych. Nie trzeba udostępniać tokenu ani hasła.
7. Dodaj pierwszą datę jako punkt początkowy. Wpisz znane saldo po tej fakturze; **0 tylko wtedy, gdy rzeczywiście wynosiło zero**. Pierwszy wpis nie ma bilansu okresu, ponieważ brak wcześniejszego odczytu. Bez salda początkowego można nadal analizować zmiany energii; saldo magazynu pozostanie nieznane do pierwszej wpisanej faktury.
8. Dodawaj kolejne daty, również wcześniejsze; rejestr sortuje je i przelicza zależne wyniki. Nie ma limitu liczby wpisów w logice aplikacji. Tabela pokazuje po 20 wierszy, a wykres ostatnie 12 zamkniętych okresów.

Nie trzeba zmieniać `configuration.yaml`, definicji obecnych sensorów ani konfiguracji Recorder. Ewentualne wydłużenie retencji jest osobną, świadomą decyzją i nie przywraca już usuniętych danych.

## Co oznaczają pola

Granica daty `D` to **północ rozpoczynająca D+1 w Europe/Warsaw**, wyłączona. Dla każdego licznika pobieramy ostatnią rzeczywistą próbkę **przed** tą granicą, nie starszą od ustawionego limitu. Brak jednej z próbek uniemożliwia zapis rozliczenia. Próbka równo o północy należy do kolejnego dnia. Zmiana czasu jest obsługiwana przez bazę stref czasowych.

| Pole | Znaczenie |
|---|---|
| Import / eksport | Dwa odczyty w kWh, zapisane z osobnymi czasami próbek |
| Bilans obliczony | 0,8 × odczyt eksportu − odczyt importu; bez osobnego źródłowego sensora bilansu |
| Bilans okresu | 0,8 × (eksport końcowy − eksport początkowy) − (import końcowy − import początkowy) |
| Szacunek przed fakturą | Poprzednie saldo przeniesione + bilans okresu |
| Saldo po fakturze | Opcjonalny stan przenoszony na następny okres; **zastępuje** szacunek |
| Różnica faktura − HA | Saldo z faktury − szacunek przed fakturą; nieznana, jeśli brak salda odniesienia |
| Korekta | Opcjonalna podpisana liczba dodawana do szacunku, gdy nie wpisano salda z faktury |
| Niedobór rozliczony na fakturze | Opcjonalna nieujemna liczba informacyjna; nie jest ponownie odejmowana od nowego okresu |
| Szacunkowe saldo teraz | Saldo przeniesione + 0,8 × zmiana eksportu od ostatniej granicy − zmiana importu od tej granicy |
| Energia dostępna / niedobór | Odpowiednio dodatnia i ujemna część bieżącego szacunkowego salda |

Saldo z faktury i korekta są wzajemnie wykluczające się. Puste pole oznacza brak informacji, a nie zero. Korekta nie może ustalić nieznanego salda początkowego; karta ostrzega, gdy nie można jej zastosować.

**Przykład:** szacunek przed fakturą wynosi −950 kWh; PGE rozlicza ten niedobór i zeruje magazyn. Wpisz `saldo po fakturze = 0`, `niedobór rozliczony = 950`. Nowy okres zacznie się od zera. Wartość ujemna w polu salda oznacza świadomie przenoszony ujemny bilans, a nie sam fakt otrzymania rachunku.

Edycja samej faktury lub uwag zachowuje zapisany odczyt, nawet jeśli Recorder usunął historię. Zmiana daty pobiera nowy odczyt. Przycisk **Odczytaj ponownie** jawnie zastępuje zamrożoną próbkę; najpierw pobierz kopię. Usunięcie pierwszego wpisu zmienia punkt początkowy, więc nowy pierwszy okres straci wcześniejsze odniesienie.

## Trwałość, backup i cofnięcie zmian

Rejestr zapisujemy natychmiast przez HA `Store` w `/config/.storage/pge_storage.<entry_id>`. Zawiera daty, identyfikatory, rzeczywiste próbki, wartości z faktur i uwagi. Wpisy przetrwają restart i czyszczenie historii Recorder. Nie edytuj ręcznie `.storage` podczas działania HA.

- Pobieraj **kopię JSON** przed importem, usuwaniem lub ponownym odczytem próbki. Import sprawdza wersję, źródło, jednostkę, strefę, unikalność dat i wartości; zastępuje cały rejestr. Jest odtworzeniem zaufanej kopii, nie niezależnym potwierdzeniem autentyczności danych faktury czy próbki.
- Pełny backup konfiguracji HA obejmuje `.storage`; sprawdź zakres swojego mechanizmu kopii. Plik JSON można przenieść do nowej instalacji z taką samą parą źródłowych `entity_id`.
- Tylko administrator może edytować, usuwać, importować i eksportować. Odczyt karty wymaga uprawnienia odczytu **obu** liczników źródłowych. Błędny zapis nie zmienia działającego rejestru; równoczesne edycje chroni numer rewizji.
- Aby czasowo wycofać działanie, **wyłącz wpis integracji**. Aby odinstalować: pobierz JSON, usuń kartę/dashboard, usuń wpis integracji i katalog `custom_components/pge_storage`, następnie zrestartuj HA. Usunięcie wpisu kasuje **jego własny rejestr**, dlatego zrób kopię wcześniej. Źródłowe liczniki oraz ich historia pozostają nietknięte.
- Kopie danych i tokeny HA trzymaj poza repozytorium.

## Testowanie po instalacji

1. Sprawdź odczyt dla daty, dla której masz historię; porównaj wartości **i czasy obu próbek** z historią liczników. Ocena dopuszczalnego wieku próbek zależy od częstotliwości ich aktualizacji.
2. Dodaj dwie daty. Sprawdź ręcznie różnicę eksportu × 0,8 minus różnicę importu. Wynik może być ujemny, mimo że liczniki są nieujemne. Dla identycznych próbek różnica musi wynosić zero.
3. Wpisz saldo z faktury 0 lub znaną nadwyżkę i sprawdź bieżące saldo. Sprawdź korektę na osobnym wpisie, bez jednoczesnego salda faktury.
4. Zmień historyczną datę, a potem usuń testowy wpis. Kolejne bilanse muszą zostać przeliczone. Zrób to po pobraniu kopii.
5. Wybierz datę bez danych oraz datę przyszłą. Zapis ma zakończyć się czytelnym błędem, bez dodania wpisu.
6. Uruchom ponownie HA, sprawdź rejestr i działanie karty; sprawdź też konto bez praw administratora.

## Rozwój i testy w chmurze

Potrzebne są `uv`, Python 3.14.2+ i Node.js 22+. W HA OS Pythonem zarządza system; poniższe polecenia są dla **oddzielnego środowiska deweloperskiego**, nie konsoli produkcyjnego HA.

```bash
cd /workspace/MagazynPGE
export UV_PYTHON_INSTALL_DIR=/workspace/.python
export UV_CACHE_DIR=/workspace/.cache/uv
uv sync --frozen
npm ci --cache /workspace/.cache/npm --no-audit --no-fund
uv run --frozen playwright install --with-deps chromium
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen python scripts/check_release.py
npm test
npm run check
```

Testy Python uruchamiają rzeczywisty, izolowany HA z SQLite Recorder i autoryzowanym WebSocket na losowym porcie lokalnym. Sprawdzają historię, CRUD, trwałość i uprawnienia; nie łączą się z Twoim HA. Testy karty obejmują DOM oraz pełny frontend HA w Chromium: automatyczne ładowanie zasobu, wyświetlenie karty i ponowne otwarcie po odświeżeniu. Test przeglądarkowy używa systemowego `chromium`, jeśli jest dostępny, albo przeglądarki zainstalowanej przez Playwright. Nie oznacza to weryfikacji wyglądu we wszystkich przeglądarkach ani wdrożenia w Twojej instalacji.

Wyniki wykonanych kontroli: [WERYFIKACJA.md](docs/WERYFIKACJA.md). Paczkę instalacyjną z samą integracją, dashboardem i dokumentacją tworzy `uv run --frozen python scripts/build_archive.py`; wynik trafia do `dist/MagazynPGE-0.2.2.zip`.

Opcjonalne uruchomienie lokalnego HA do ręcznego sprawdzenia GUI:

```bash
uv run --frozen python scripts/init_dev.py
uv run --frozen hass -c .ha-dev --skip-pip
```

Skrypt zachowuje istniejący plik konfiguracyjny; konfiguracja testowa zawiera parę demonstracyjną `sensor.pge_demo_import_total` i `sensor.pge_demo_export_total`, sterowaną dwoma `input_number`. Nie są to Twoje produkcyjne liczniki i nie mają historii z poprzednich lat. Dodaj integrację przez lokalny GUI HA. Proces działa na pętli lokalnej, a jego dane w ignorowanym `.ha-dev/`; nie kopiuj tego katalogu do produkcji.

Każde zadanie chmurowe jest już izolowane: pracuj w istniejącym checkoutcie, bez tworzenia worktree, chyba że użytkownik wyraźnie o to poprosi. Instalacja zależności wymaga standardowych domen GitHub, PyPI i npm; integracja po instalacji nie wymaga internetu ani sekretów PGE.

## Przejście z prototypu 0.1

Wersja 0.1 korzystała z gotowego sensora bilansu. Wersja 0.2 używa innego kontraktu pomiarowego i formatu danych. Jeśli zainstalowałeś 0.1, najpierw wyeksportuj jej rejestr i zrób pełny backup. Wyłącz stary wpis; po aktualizacji dodaj **nowy** z parą liczników. Ponownie dodaj daty i faktury po sprawdzeniu dostępności historii obu liczników. Stary wpis i jego plik danych nie są automatycznie kasowane ani przeliczane. Import starego JSON jest odrzucany: sam historyczny bilans nie pozwala odtworzyć dwóch rzeczywistych liczników. Zachowaj stary katalog integracji poza `/config/custom_components` do ewentualnego wycofania aktualizacji.
