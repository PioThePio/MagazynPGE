# Magazyn energii PGE dla Home Assistant

Wirtualny magazyn energii z historią faktur i kartą Lovelace. Integracja odczytuje **dwa oddzielne liczniki energii sieciowej** i bilansuje **każdą godzinę zegarową osobno**: najpierw pobór i eksport kompensują się 1:1, potem nadwyżka eksportu zasila magazyn ze współczynnikiem 0,8. Gotowy sensor bilansu `export-import` nie jest źródłem. Wszystkie istniejące sensory, ich historia i statystyki pozostają tylko do odczytu.

To integracja lokalna: bez konta PGE, bez chmury zewnętrznej, bez Pyscript, AppDaemon, MQTT i dodatkowej bazy danych. Nie pobiera faktur z PGE.

## Diagram i bateria od 0.13.0

Pod Siecią są fizyczne „Pobrano” i „Oddano” w wybranym okresie, bez opustu. Strzałki PGE to inne wartości: po kompensacji każdej godziny, do magazynu po opuście i pobrane z dostępnego zapasu. Magazyn nie schodzi poniżej zera; brakujący zapas pokazuje Niedobór. Słońce jest nad Domem, obie instalacje po lewej; ich kolejność zmienisz przyciskami ↑/↓ w konfiguratorze. Wszystkie moce na dashboardzie są zaokrąglone do całych jednostek, bez zmiany dokładności obliczeń.

Obwódki Domu i ładowanej baterii pokazują szacowane udziały mocy: PV żółty, bateria turkusowy, sieć niebieski. Przy jednoczesnym zasilaniu i ładowaniu stosujemy proporcjonalny podział wspólnego zasilania. Nie jest to pomiar pochodzenia energii zgromadzonej w baterii. PGE nie jest fizycznym źródłem zasilania.

Czas baterii wymaga SOC, rzeczywistej mocy baterii i pojemności odpowiadającej 0–100% SOC (kWh albo Ah × napięcie nominalne / 1000). Minimum SOC wybierasz z encji sensor/number, np. aktywnego limitu Victrona — identyfikator wybiera użytkownik, integracja go nie zgaduje. Średnia 1/5/15 min, domyślnie 5 min; pierwsze co najmniej 30 s zbiera pomiary. Przy mocy ≤25 W lub brakujących danych czas pozostaje nieznany. Po zmianie kierunku przepływu zbieramy nowe okno. Dwie nowe encje czasu mają jednostkę sekund.

Opcjonalne uczenie profilu ładowania wymaga encji dopuszczalnego prądu ładowania z BMS oraz napięcia baterii. Uczymy się tylko przy mocy zbliżonej do niezależnie odczytanego ograniczenia BMS; brak PV nie jest nauką ograniczenia baterii. Każdy zakres 5 punktów SOC wymaga co najmniej trzech próbek, pobieranych najwyżej raz na minutę. Bez pełnego profilu pozostałych zakresów działa estymacja ze średniej mocy. Profil jest zapisywany przy cyklicznym zapisie archiwum (do 5 min), zachowany po restarcie i w kopii JSON. Zmiana źródeł baterii lub pojemności unieważnia profil.

Scenariusz PV wymaga dwóch wybranych encji energii: prognozowanej produkcji i prognozowanego zużycia domu, dla tego samego pozostałego horyzontu (1–24 h). To oszacowanie przy równomiernym rozłożeniu nadwyżki; nie rozpoznajemy automatycznie atrybutów Solcast/Forecast.Solar ani różnych horyzontów. Jeśli nadwyżka nie wystarcza w tym horyzoncie, nie podajemy czasu poza nim. Model i scenariusz pokazują przedział, nie gwarantowaną godzinę.

„Energia potrącona w systemie opustów” to encja od ostatniej faktury, a „Potrącenie opustu dzisiaj” to osobna encja dzienna. Karta `custom:pge-opust-card` pokazuje wybrany dzień/tydzień/miesiąc/rok. Wzór: 20% sumy nadwyżek eksportu po bilansowaniu zamkniętych godzin. Nie obejmuje wygaśnięć ani strat baterii. Dodaj kartę przez natywny wybór kart HA; nowe generowane dashboardy zawierają ją od razu. Od 0.14.0 po restarcie automatycznie zastępujemy starą kartę `custom:pge-storage-card` osobnymi modułami. Istniejące osobne moduły mają pierwszeństwo, więc diagram nie jest dodawany drugi raz. Pozostałe karty i ustawienia widoku zostają zachowane. Dotyczy dashboardów Storage; YAML pozostaje bez zmian. Przy wielu wpisach integracji migrujemy tylko karty z jednoznacznym `entry_id`. Kopia układu sprzed migracji jest w HA Store: `.storage/pge_storage.<entry_id>.dashboard_backup`. Przycisk „Uporządkuj obecny dashboard” w ustawieniach uruchamia tę samą operację ponownie.

## Bilans godzinowy od 0.12.0

Godziny są pełnymi godzinami zegarowymi Europe/Warsaw, identyfikowanymi w UTC. Dzień zmiany czasu ma 23 lub 25 godzin; powtórzona godzina pozostaje dwoma osobnymi przedziałami. Niczego nie pomijamy przed ani po granicy godziny.

Dla P = pobór i E = eksport z pary liczników wybranej w integracji: zużycie = `max(P−E,0)`, nadwyżka = `max(E−P,0)`, do magazynu = `0,8 × nadwyżka`. 1/1 kWh daje zero; 1/3 daje +1,6 kWh; 3/1 daje −2 kWh. Eksport 1 kWh w jednej godzinie i pobór 1 kWh w następnej daje −0,2 kWh. Węzeł Sieć pokazuje fizyczny bilans energii, bez opustu; PGE pokazuje rozliczenie po bilansowaniu godzinowym i opuście.

Źródłem są przyrosty natywnych statystyk `sum` obu wybranych liczników, z konwersją Wh/kWh i obsługą resetów przez Recorder. Zastępczo można użyć pełnych, dokładnych granic stanów Recorder bez resetu wewnątrz godziny. Brak wymaganych odczytów oznacza nieznany wynik rozliczenia, **nie zero**. Zamknięte godziny są zapisywane w Store i kopii JSON, więc usunięcie źródłowej historii nie kasuje wcześniej utrwalonych godzin. Nie odtwarzamy nieistniejących godzin ze starych sum dobowych.

Nowe encje **Bilans bieżącej godziny** (`P−E`, dodatni = pobór, ujemny = eksport) oraz **Wpływ bieżącej godziny na magazyn** pokazują wynik roboczy. Mają początek, koniec, czas danych i jakość w atrybutach. Po restarcie/resetach czekają na wiarygodny natywny punkt odniesienia. Wynik roboczy zastępuje poprzedni wynik tej godziny, ale nie zmienia salda magazynu. Magazyn, niedobór i strzałki PGE uwzględniają wyłącznie zamknięte godziny z kompletem danych. Znak encji godzinowej od 0.13.0 jest odwrócony względem 0.12.0; nie przepisujemy historycznych stanów. Nie tworzymy automatyzacji, progów ani buforów czasowych.

Saldo z faktury zachowuje wartość do odbioru; nie odejmujemy ponownie 20%. Partie z faktury umożliwiają FIFO i ważność 12 miesięcy od końca miesiąca wprowadzenia. Bez partii saldo jest oznaczone jako oszacowanie bez wygaśnięć. Projekcja zużywa bieżący zapas według historycznego **poboru po bilansowaniu godzinowym**, bez przyszłych doładowań. Stary profil surowego importu nie jest automatycznie uznawany za taki profil — wczytaj historię ponownie lub zapisz ręczne założenia.

Wskaźnik bieżącej godziny znajduje się nad połączeniem Sieć–Dom, pozostawiając odsłoniętą strzałkę fizycznego przepływu. Kliknięcie otwiera szczegóły encji; w konfiguratorze lub YAML `show_hour: false` można go ukryć. Osobna karta to `custom:pge-hour-card`. PGE znajduje się pod siecią i ma przerywane połączenie rozliczeniowe z siecią. Nie jest fizycznym źródłem zasilania domu.

## Źródła w Twojej instalacji

| Zestaw | Import z sieci | Eksport do sieci |
|---|---|---|
| SDM640 — podstawowy wybór | „630 E import”, kWh | „630 E export”, kWh |
| Victron — alternatywna para | `energymeter_consumption`, kWh | `energymeter_feed_in`, kWh |

Wybierz **jedną pełną parę** w GUI. Nie dodajemy wskazań SDM640 do Victrona: mierzą ten sam przepływ energii. Integracja nie zgaduje `entity_id` z nazwy wyświetlanej. Wybierając Victrona, wskaż rzeczywiste encje z listy HA odpowiadające podanym nazwom. Nie zakładaj automatycznie prefiksu ani konkretnej pisowni identyfikatora.

Oba liczniki muszą obejmować ten sam punkt przyłączenia do sieci, mieć narastające wartości z poprawnymi statystykami `sum` Recorder (reset wymaga potwierdzonej ciągłości sum). Nie wybieraj energii ładowania/rozładowania baterii, mocy W/kW, SOC ani dziennych liczników energii. Nie przełączamy źródła automatycznie w razie braku danych — różne liczniki mogą mieć inne początki naliczania i historię.

## Dlaczego mała integracja

Natywne szablony dobrze wyliczają różnice, ale nie zarządzają trwałą, edytowalną listą dowolnej długości ani historycznymi odczytami Recorder. `utility_meter` nadaje się do cykli i taryf, ale nie zapewnia tego rejestru zmiennych dat, faktur i korekt. Helper dla każdego okresu oznaczałby rozrastającą się ręczną konfigurację.

Rozwiązanie składa się z jednego wpisu integracji, jednego pliku danych HA, 34 stałych sensorów i niezależnych modułów Lovelace. Nie powstają nowe encje dla kolejnych faktur. Szczegóły i źródła API: [architektura](docs/ARCHITEKTURA.md).

## Moc, średnie i historia energii

Diagram i lista odbiorców korzystają ze wspólnych, ważonych czasem okien mocy: **1/5/10/15 s oraz 1/5/15/30 min**. Domyślnie diagram wybiera 10 s, odbiorcy 5 s. Po ustawieniu tego samego okna moc domu w obu kartach ma tę samą wartość i czas. Kolumna Moc pokazuje wspólne okno 1 s, a Średnia wybrane okno. Encje historii domu i nieśledzonego zużycia zachowują dotychczasowe okno 15 s.

Moce na obu kartach odświeżają się wspólnie co 3 s. Domyślny tryb wyrównany ma 12 s opóźnienia: interpoluje raporty PV i zestawia je z pomiarami sieci/baterii z tego samego czasu. Tryb „Najnowsze odczyty” pokazuje ostatnie dane z możliwością skoków bilansu. Nie odpytujemy urządzeń dodatkowo. Interpolacja jest oszacowaniem. Średnie mocy nie zmieniają źródłowych kWh ani rozliczeń godzinowych.

Po uruchomieniu lub zmianie źródeł odtwarzamy ostatnie 30 minut mocy z Recorder (próbkowanie historyczne co 5 s). Dzięki temu długa średnia nie musi czekać 30 minut, jeśli historia istnieje. Niepełne pokrycie jest oznaczone; nieistniejąca historia nie staje się zerem. Jawnie niedostępne źródło mocy na żywo wnosi 0 W, również falownik wyłączony w nocy. Przy braku wspólnej historii tryb wyrównany najpierw zbiera próbki. Bufor mocy na żywo ogranicza zapis do dwóch próbek na sekundę; nie dotyczy to liczników kWh ani rozliczeń.

Lista odbiorców pokazuje energię wybranego dnia, tygodnia, miesiąca lub roku. Kliknięcie nagłówka Nazwa / Moc / Średnia / Energia sortuje; kolejne odwraca kierunek. Nieśledzone zużycie sortuje się tak samo, podliczniki pozostają pod rodzicem. Kolejność jest utrzymywana przez 5–15 s zależnie od okna, a ręczne sortowanie działa od razu.

Nieśledzone ma dwie własne encje: **Nieśledzone zużycie** (W, pomiar, z długoterminowymi statystykami mocy) oraz **Nieśledzone zużycie dzisiaj** (kWh, podpisana różnica dzienna). Kliknięcie wiersza otwiera historię mocy w HA. Historia zbiera się od aktualizacji, zgodnie z filtrami Recorder użytkownika; nie odtwarzamy wstecz nieistniejących odczytów. Ładowanie baterii jest odjęte od domu przed obliczeniem różnicy, a podliczniki nie dublują rodzica.

Dla kWh sumujemy dostępne odczyty statystyk w wybranym okresie. Brak stycznia nie usuwa danych z czerwca–października. Niepełną historię oznacza etykieta przy wyborze okresu. Dzisiejsze kWh korzystają również ze statystyk pięciominutowych, odświeżanych co 5 minut. Energia nie wynika z całkowania wygładzonej mocy. Obliczenia domu odejmują ładowanie baterii; faktury i rozliczenia PGE zachowują niezależne, wymagane odczyty graniczne.

## Zgodność i ograniczenia

- **Przetestowana wersja: Home Assistant Core 2026.10.0, Python 3.14.8.** Środowisko deweloperskie jest przypięte do tej wersji. Ta wersja HA wymaga Python ≥3.14.2.
- Wskazana instalacja to **HA OS 18.3, Core 2026.10.0, Supervisor 2026.10.2, frontend 20260930.2**. Testy uruchomiono na tym samym Core i frontendzie. Supervisor i HA OS zarządzają Twoim urządzeniem; nie instalujemy ich w chmurze. Dla zgodności integracji istotny jest Core, nie numer Supervisora.
- Każdy licznik musi mieć nieujemny liczbowy stan w **Wh, kWh lub MWh**; odczyty przeliczamy do kWh. Obliczony bilans i bilanse okresów mogą być dodatnie albo ujemne. Spadek licznika pomiędzy granicami jest błędem ciągłości. Resetu ukrytego pomiędzy próbkami nie da się wykryć wyłącznie z odczytów granicznych, dlatego wymagamy liczników bez resetów.
- Odtwarzamy **ostatni zapisany stan**, nie dokładną fizyczną wartość w chwili północy. Czas każdej z dwóch próbek jest widoczny; liczniki nie muszą aktualizować się jednocześnie. Dokładność zależy od częstotliwości źródła i ciągłości rejestracji.
- Gdy Recorder usunął wymagane dane, integracja odmawia utworzenia odczytu. Statystyki długoterminowe nie przywrócą dokładnej wartości końcowej. Nie ma interpolacji ani wpisywania zmyślonych wartości.
- Wersje 0.3–0.5 dodają dzienne przepływy, partie FIFO i osobne moduły energii. Terminy opierają się na partiach z faktury; domyślna reguła to 12 miesięcy od końca miesiąca wprowadzenia. Od wersji 0.4 projekcja odejmuje od obecnego zapasu wyłącznie pobór z sieci z odpowiednich miesięcy poprzedniego roku, rozłożony równomiernie na dni. Nie dodaje przyszłego eksportu ani wzrostu zużycia i pozostaje scenariuszem, nie prognozą pogody ani potwierdzonym saldem PGE.

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

## Osobne moduły dashboardu (0.9)

Po aktualizacji kliknij **Rozliczenia i ustawienia → Utwórz dashboard z osobnych kart → Otwórz dashboard**. Powstaje natywny dashboard HA z ośmioma niezależnymi kartami: trzy kafelki, przepływy, odbiorcy, projekcja, historia i konfigurator. **Ołówek HA** pozwala przenosić i edytować każdą kartę osobno. Ponowne kliknięcie przycisku otwiera ten sam dashboard i zachowuje Twoje zmiany.

Dotychczasowa `custom:pge-storage-card` pozostaje zgodnym zestawem modułów, dopasowanym do szerokości samej karty. Aby edytować elementy osobno w HA, korzystaj z utworzonego dashboardu lub **Dodaj kartę → wyszukaj PGE**. Kafelki można też dodać jako standardowe karty encji HA.

| Moduł w selektorze | Typ YAML | Przeznaczenie |
|---|---|---|
| PGE · Odbiorcy w domu | `custom:pge-consumers-card` | Osobna lista urządzeń, moc, średnia 1 s–30 min i energia okresu |
| PGE · Energia w domu | `custom:pge-energy-card` | Schemat PV, domu, sieci, akumulatora i magazynu PGE; moc teraz + energia dzisiaj jednocześnie |
| PGE · Pojedynczy kafelek | `custom:pge-balance-card` | Jedna wybrana wartość, kliknięcie otwiera encję HA |
| PGE · Miesiące i dni | `custom:pge-history-card` | Miesięczne podsumowanie i wykres; kliknięcie miesiąca otwiera dni i wykres dzienny |
| PGE · Projekcja magazynu | `custom:pge-projection-card` | Pobór rok wcześniej, obecnie i projekcja salda do rozliczenia |
| PGE · Konfigurator | `custom:pge-settings-card` | Przyciski otwierające okno źródeł, faktur i partii |
| PGE · Gotowy dashboard | `custom:pge-storage-card` | Responsywny zestaw powyższych modułów, bez jednej zewnętrznej karty |

Przy jednej integracji nie trzeba podawać `entry_id`. Przy kilku wybierz identyfikator w edytorze każdej karty. Kafelek ma w edytorze GUI wybór wartości: magazyn, niedobór, zmiana od faktury, saldo po fakturze, pobrano i oddano od faktury. Przykład samodzielnej karty:

```yaml
type: custom:pge-balance-card
metric: available_energy
```

Wartości `metric`: `available_energy`, `deficit`, `period_balance`, `carried_balance`, `import_since_settlement`, `credited_since_settlement`. Przykład układu z natywnymi sekcjami HA: [dashboards/pge.yaml](dashboards/pge.yaml).

### Konfigurator źródeł

Przy pierwszym uruchomieniu integracja pobiera źródła z konfiguracji natywnego **panelu Energia HA**: sieć, PV, akumulator i odbiorców. Zachowuje dotychczasowe ręczne wybory. Aby ponownie pobrać ustawienia, otwórz **Źródła energii → Wczytaj z panelu Energia → Zapisz źródła**. Każde źródło można zmienić ręcznie z listy encji. Konfiguracja natywnego panelu pozostaje bez zmian.

**Osobny sensor zużycia domu nie jest potrzebny.** Pozostaw pola domu jako **Oblicz z bilansu**:

`dom = PV + pobór z sieci + rozładowanie akumulatora − oddanie do sieci − ładowanie akumulatora`

Ten sam bilans liczymy oddzielnie dla mocy W i energii kWh. Ręcznie wybrana encja domu zastępuje obliczenie. W widoku bieżącej mocy brakujący, niedostępny lub niepoprawny odczyt źródła daje wkład 0 W; działające źródła nadal są sumowane. Wszystkie źródła bez odczytu dają 0 W. Brak historii kWh pozostaje brakiem danych. Źródło nieobecne w konfiguracji Energii (np. brak akumulatora) nie wymaga dodatkowego sensora zerowego.

- Z panelu Energia pobieramy również wiele źródeł PV, statystyki zewnętrzne i kierunki mocy. Moc W/kW jest bieżąca; dzisiejsze kWh pochodzą z godzinowych sum Recorder, z obsługą resetów liczników. Widoczny czas **do HH:mm** określa ostatnią pełną godzinę. Odświeżamy odczyt co pięć minut, gdy HA udostępni statystyki.
- Ręcznie wybrany licznik bez powiązania ze statystykami musi być narastający Wh/kWh/MWh bez resetów. Wtedy Dzisiaj = aktualny stan minus odczyt przed północą. Brak historii nie oznacza zera.
- Lokalny akumulator: poziom %, opcjonalnie bieżąca energia zgromadzona w kWh. Jeśli Energia zawiera pojemność i poziom, obliczamy stan jako pojemność × poziom / 100.
- Do 16 odbiorców: moc i/lub energia. Nie sumujemy ich do zużycia domu, aby nie liczyć tej samej energii dwa razy.
- Źródła fizycznych przepływów z Energii nie zmieniają pary liczników używanej do faktur i magazynu PGE ani opustu 0,8.

Zapis aktualizuje moduły i encje **bez restartu HA**. Nie wybieraj encji obliczonych przez sam Magazyn PGE jako jego źródeł; backend odrzuca takie zapętlenie.

### Moc, energia i wybór okresu

Diagram oraz odbiorcy pokazują W na żywo i kWh z wybranego okresu. Wybierz **dzień, tydzień, miesiąc lub rok**, następnie zmieniaj daty strzałkami albo kalendarzem. Zmiana historycznej daty zmienia kWh; moc, SOC i obecny zapas PGE pozostają aktualne. Tygodnie zaczynają się w poniedziałek; granice okresów są liczone w Europe/Warsaw, także w dni zmiany czasu. Statystyki wymagają pokrycia wybranego zakresu — braki pozostają puste.

W kołach główna wartość to moc W, poniżej energia kWh. Sieć ma jedną moc: **plus = pobieranie, minus = oddawanie**. Strzałki zmieniają kierunek według bieżącego przepływu. Słońce pokazuje sumę, a po bokach moce poszczególnych instalacji. PGE pokazuje aktualny zapas oraz dodaną energię po opuście i energię pobraną z magazynu w wybranym okresie. Pobranie z PGE wymaga znanego salda początkowego i historii magazynu; import z sieci nie jest automatycznie uznawany za pobranie z zapasu.

### Odbiorcy, foldery i nieśledzone zużycie

Na górze są suma mocy domu i energia domu z wybranego okresu. Urządzenia pokazują jedną cyfrę po przecinku. Relacje **urządzenie nadrzędne** z panelu Energia są importowane automatycznie, np. **AC → AC-Dół, AC-Góra**. Foldery można rozwijać i zwijać; ustawienia źródeł pozwalają ręcznie zmienić rodzica.

Śledzone zużycie sumujemy bez podwójnego doliczania podliczników. Dla W oraz kWh osobno wybierany jest skonfigurowany pomiar nadrzędny; gdy rodzic nie ma skonfigurowanej danej wielkości, liczą się jego dzieci. **Nieśledzone = cały dom − śledzone**. Ujemny wynik pozostaje widoczny z informacją o przekroczeniu, aby nie ukrywać różnic między punktami pomiarowymi.

### Pojemność baterii: kWh albo Ah i V

„Własna encja zapasu kWh” to opcjonalny sensor pokazujący bieżącą energię w baterii. Zostaw go pustego, jeśli nie masz takiej encji. Wybierz SOC oraz pojemność, a zapas obliczy się jako SOC × pojemność / 100.

Pojemność można wpisać bezpośrednio w kWh albo wybrać **Ah + napięcie nominalne**. Obowiązuje `kWh = Ah × V / 1000`. Samo 99 Ah nie określa energii. Przykładowo 99 Ah przy napięciu nominalnym 51,2 V daje 5,0688 kWh; użyj rzeczywistego napięcia nominalnego całego zestawu z dokumentacji, a nie chwilowego napięcia podczas ładowania. Podgląd pokazuje przeliczenie przed zapisaniem. Przy braku napięcia nie zgadujemy pojemności. SOC oraz moc baterii działają niezależnie od tego opcjonalnego ustawienia.

### Sieć i lokalny akumulator — co wybrać

Na screenie z wersji 0.6 moc sieci pochodziła z **630 P**. Liczniki kWh nie służą do obliczania bieżącej mocy.

| Ustawienie | Znaczenie i wybór dla Victrona |
|---|---|
| Energia pobrana / oddana z sieci | Narastające kWh: `energymeter_consumption` / `energymeter_feed_in` |
| Moc sieci +/− | Bieżąca moc w punkcie przyłączenia W/kW, łącznie dla wszystkich faz; wybierz sensor łączny albo poszczególne fazy, nie oba warianty |
| Osobna moc pobierana / oddawana | Alternatywa dla sensora +/−. Pojawia się po wybraniu „Dwa osobne kierunki”; oba sensory nieujemne |
| Poziom akumulatora | SOC w % |
| Energia w akumulatorze | Aktualna zawartość kWh, opcjonalnie; jeśli brak własnego sensora, podaj pojemność i SOC |
| Moc akumulatora +/− | Chwilowe ładowanie/rozładowanie W/kW. Ustaw znaczenie dodatniej wartości zgodnie z faktycznym ładowaniem; znormalizowana Energia HA ma dodatnie rozładowanie |
| Liczniki ładowania / rozładowania | Skumulowane kWh wtłoczone do baterii i z niej pobrane, używane do bilansu dnia |

Przy znaku „dodatnia = pobór” karta wylicza z mocy sieci `P`: pobór `max(P, 0)`, oddawanie `max(−P, 0)`. Przy przeciwnym znaku najpierw odwraca P. Nie trzeba podawać oddzielnych mocy kierunkowych.

Import pokazuje wszystkie źródła PV jako jawne wiersze, także brakującą encję z historyczną statystyką. Brak encji w bieżących stanach nie blokuje zapisu importu. Brak historii pozostawia pustą wartość; brak mocy jednego źródła wnosi 0 W, a pozostałe moce są nadal sumowane. Raport wskazuje, czego nie ma w konfiguracji Energii. Sama konfiguracja kWh nie dostarcza mocy W, SOC ani pojemności akumulatora. Zmienione nazwy pomocniczych sensorów mocy Energii są odczytywane z rejestru HA.

### Encje do użycia poza kartami

Integracja zachowuje pięć dotychczasowych encji i dodaje kolejne: **łącznie 24 stałe sensory** niezależnie od liczby faktur i odbiorców. Nowe wartości to pobór/oddanie od faktury, moce PV/domu/sieci/akumulatora, poziom i stan lokalnego akumulatora oraz dzisiejsze energie PV/domu/sieci/ładowania/rozładowania i kredyt PGE po opuście. Niepodłączone źródła mają stan niedostępny. HA może nadawać różne entity_id zależnie od wcześniejszych nazw; wybierz encję w **Ustawienia → Urządzenia i usługi → Magazyn PGE → Encje**.

Można używać ich w standardowych kafelkach, automatyzacjach i innych kartach. Źródłowe liczniki pozostają bez zmian. Dzienne energie i saldo nie udają narastających liczników: nie mają `state_class: total_increasing`. Do natywnego panelu Energia wybieraj źródłowe liczniki narastające. Encje odbiorców są ich istniejącymi encjami, nie tworzymy duplikatów każdego urządzenia.

### Rozliczenie miesięczne i dni

Najpierw widzisz **miesięczne sumy i wykres**. Kliknij nazwę miesiąca, aby zobaczyć dni. Kolejność kolumn: **pobrano z magazynu, oddano do magazynu, magazyn na koniec dnia, zmiana netto**. Oddanie jest już po opuście 20%. Pobrano obciąża konto magazynu importem; ujemne saldo oznacza niedobór. Brak rozwijanych czasów i uwag przy dniach. Miesięczny bilans liczymy z granicznych odczytów — brak pojedynczych dni nie musi kasować znanej sumy miesiąca. Dzień faktury może ustalić nowe saldo, a wygaśnięcie je zmniejszyć niezależnie od przepływów.

Wykres ma osobną oś magazynu, aby jego duży zapas nie spłaszczał poborów. Znalezione odczyty zakończonych dni pozostają archiwizowane we własnym Store, bez zapisów do Recorder. Dzisiaj jest niepełnym dniem.

### Porównanie i projekcja

Karta pokazuje trzy serie: **pobór rok wcześniej**, **pobór obecnie** i **projekcję magazynu do rozliczenia**. Pobory korzystają z lewej osi, magazyn z prawej; wszystkie wartości w kWh. Przyszłe wartości obecnego roku oraz luki pozostają puste. Bieżący miesiąc jest niepełny. Dane statystyczne są pobierane automatycznie; nie trzeba wpisywać dawnego profilu. Wymagana jest kompletna siatka godzinowych sum i poprzedzająca suma dla całego historycznego miesiąca, z konwersją do kWh.

Projekcja zużywa **obecny zapas**, bez przyszłych doładowań i bez zwiększania poboru. Uwzględnia znane wygaśnięcia. Brak historii propaguje nieznane saldo od pierwszej luki; nie rysujemy zerowej linii ani zapewnienia, że zapasu wystarczy. Liczby są pod wykresem w rozwijanej tabeli. Termin rozliczenia pozostaje edytowalny; domyślnie ostatnia faktura + 6 miesięcy z zachowaniem końca miesiąca.

### Faktury i partie w osobnym oknie

Kliknij **Faktury**, aby dodawać, poprawiać i usuwać rozliczenia oraz pobierać/przywracać kopię JSON. **Plan i partie** otwiera datę następnego rozliczenia i partie z ostatniej faktury. Suma surowych partii × 0,8 musi odpowiadać saldu faktury. Domyślna ważność to 12 miesięcy od końca miesiąca wprowadzenia, edytowalna zgodnie z rozliczeniem. FIFO zużywa najstarsze partie; od faktury odtwarzamy osobno pobór i doładowanie. Dodatni bilans netto nie zachowuje sztucznie całej starej partii.

Aktualizacja zachowuje rejestr, partie, archiwa i nazwy istniejących encji. JSON formatu 5 zawiera także `hourly_cache` i podstawę profilu prognozy; odczyt kopii 2/3/4 pozostaje obsługiwany. Stare archiwa dobowe nie zastępują brakujących godzin. Przed powrotem do starszego kodu zachowaj kopię.

## Co oznaczają pola

Granica daty `D` to **północ rozpoczynająca D+1 w Europe/Warsaw**, wyłączona. Dla każdego licznika pobieramy ostatnią rzeczywistą próbkę **przed** tą granicą, nie starszą od ustawionego limitu. Brak jednej z próbek uniemożliwia zapis rozliczenia. Próbka równo o północy należy do kolejnego dnia. Zmiana czasu jest obsługiwana przez bazę stref czasowych.

| Pole | Znaczenie |
|---|---|
| Import / eksport | Dwa odczyty w kWh, zapisane z osobnymi czasami próbek |
| Surowe odczyty graniczne | Zachowane dla audytu faktury; dawny indeks `sample.value` służy tylko zgodności kopii |
| Bilans przepływów okresu | Suma `0,8 × max(E−P,0) − max(P−E,0)` liczona osobno dla każdej godziny |
| Szacunek przed fakturą | Poprzednie saldo przeniesione + bilans okresu |
| Saldo po fakturze | Opcjonalny stan przenoszony na następny okres; **zastępuje** szacunek |
| Różnica faktura − HA | Saldo z faktury − szacunek przed fakturą; nieznana, jeśli brak salda odniesienia |
| Korekta | Opcjonalna podpisana liczba dodawana do szacunku, gdy nie wpisano salda z faktury |
| Niedobór rozliczony na fakturze | Opcjonalna nieujemna liczba informacyjna; nie jest ponownie odejmowana od nowego okresu |
| Szacunkowe saldo teraz | Saldo faktury + godzinowe przyrosty − godzinowy pobór − wygaśnięcia znanych partii FIFO |
| Zmiana od faktury | Obecne saldo minus saldo faktury, także z wygaśnięciami |
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
2. Dodaj dwie daty. Sprawdź osobno godzinowe kompensacje P/E, następnie opust od nadwyżek eksportu. Wynik może być ujemny, mimo że liczniki są nieujemne. Dla identycznych próbek różnica musi wynosić zero.
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

Wyniki wykonanych kontroli: [WERYFIKACJA.md](docs/WERYFIKACJA.md). Paczkę instalacyjną z samą integracją, dashboardem i dokumentacją tworzy `uv run --frozen python scripts/build_archive.py`; wynik trafia do `dist/MagazynPGE-0.16.1.zip`.

Opcjonalne uruchomienie lokalnego HA do ręcznego sprawdzenia GUI:

```bash
uv run --frozen python scripts/init_dev.py
uv run --frozen hass -c .ha-dev --skip-pip
```

Skrypt zachowuje istniejący plik konfiguracyjny; konfiguracja testowa zawiera parę demonstracyjną `sensor.pge_demo_import_total` i `sensor.pge_demo_export_total`, sterowaną dwoma `input_number`. Nie są to Twoje produkcyjne liczniki i nie mają historii z poprzednich lat. Dodaj integrację przez lokalny GUI HA. Proces działa na pętli lokalnej, a jego dane w ignorowanym `.ha-dev/`; nie kopiuj tego katalogu do produkcji.

Każde zadanie chmurowe jest już izolowane: pracuj w istniejącym checkoutcie, bez tworzenia worktree, chyba że użytkownik wyraźnie o to poprosi. Instalacja zależności wymaga standardowych domen GitHub, PyPI i npm; integracja po instalacji nie wymaga internetu ani sekretów PGE.

## Przejście z prototypu 0.1

Wersja 0.1 korzystała z gotowego sensora bilansu. Wersja 0.2 używa innego kontraktu pomiarowego i formatu danych. Jeśli zainstalowałeś 0.1, najpierw wyeksportuj jej rejestr i zrób pełny backup. Wyłącz stary wpis; po aktualizacji dodaj **nowy** z parą liczników. Ponownie dodaj daty i faktury po sprawdzeniu dostępności historii obu liczników. Stary wpis i jego plik danych nie są automatycznie kasowane ani przeliczane. Import starego JSON jest odrzucany: sam historyczny bilans nie pozwala odtworzyć dwóch rzeczywistych liczników. Zachowaj stary katalog integracji poza `/config/custom_components` do ewentualnego wycofania aktualizacji.

## Zmiany 0.15.0: źródła i bateria

Nowych odbiorców z panelu Energia dopisujemy przy uruchomieniu i podczas kontroli co 5 minut (maksymalnie 16). Zachowujemy ręczne nazwy, powiązania mocy, kolejność i rodziców. Jawnie usunięty odbiorca nie wraca automatycznie. Usunięcia w Energii i konflikty pokazujemy do sprawdzenia, bez kasowania ręcznych ustawień. Każdej instalacji PV można nadać własną nazwę w konfiguratorze i ustawić jej kolejność. Nie zmienia to nazw encji w HA. Raport importu Energii opisuje powiązania w jej konfiguracji; wybrane ręcznie źródła W są pokazane osobno.

Dłuższe wyjaśnienia otwiera ikonka ⓘ. Opcje modelu i scenariusza PV są w ustawieniach zaawansowanych. Niezapisane zmiany mają widoczny komunikat. Po zmianie źródeł kliknij **Zapisz źródła**; konfiguracja działa bez restartu.

Pojemność baterii można odczytywać z encji **Capacity** (pełna pojemność BMS, nie aktualny zapas). Przy jej niedostępności używamy wybranej **Installed capacity** i pokazujemy, że to wartość zastępcza. Jeśli wybrano encje, ale obie są niedostępne, pojemność pozostaje nieznana. Wpisana wcześniej ręczna pojemność pozostaje zapisana i wraca do użycia po odłączeniu tych encji.

Dla SIMPO 5000 napięcie nominalne wynosi **51,2 V**: 99 Ah × 51,2 V = około **5,07 kWh** pełnej pojemności. To oszacowanie energii, nie całka z pomiaru. SOC wyznacza aktualny zapas, a aktualne minimum SOC — zapas dostępny do rozładowania. Dodano osobne encje pełnej pojemności i energii dostępnej ponad minimum SOC. Napięcie nominalne służy do przeliczenia Ah; **DC bus voltage** jest chwilowym napięciem używanym dla limitu BMS. Nie zastępuje go Maximum allowed charging voltage. Faktyczna moc nadal pochodzi z Power w W; dopuszczalny prąd BMS nie jest bieżącym poborem.

Opcjonalny profil ograniczenia ładowania odczytuje do 7 dni istniejącej historii SOC, mocy, dopuszczalnego prądu ładowania BMS i rzeczywistego napięcia baterii. Przetwarzamy porcje po 6 godzin i wspólne odczyty co minutę. Uczymy tylko podczas ładowania powyżej 25 W, blisko niezależnego limitu BMS; brakujących próbek nie zastępujemy zerem. Profil ma przedziały SOC co 5 punktów procentowych, a przedział wymaga co najmniej 3 obserwacji. Bez odpowiedniej historii estymacja z bieżącej średniej nadal działa. Czasy wykorzystują średnią 1/5/15 min; przy mocy do 25 W nie określamy czasu.

Zapisany profil jest pamięcią wyników historii: kolejne odświeżenia dopisują nowe zamknięte minuty, nie liczą ich ponownie i zachowują starsze obserwacje po usunięciu historii przez Recorder. Podgląd pokazuje pokrycie. Przycisk przebudowy zastępuje profil tym, co da się odczytać teraz; nie odtworzy historii usuniętej przez HA. Dynamiczna zmiana Capacity z 99 na 98 Ah nie usuwa profilu. Zmiana fizycznych źródeł baterii resetuje model dla nowej konfiguracji.

Strzałki pod mocą sieci pokazują **↓ eksport do sieci / ↑ import z sieci**, czyli fizyczne przepływy kWh wybranego okresu, **bez opustu**. Strzałki magazynu PGE pokazują rozliczenie zamkniętych godzin, z opustem zastosowanym wyłącznie do nadwyżek po kompensacji godzinowej. Nie należy porównywać ich jako identycznych wielkości.

## Poprawka 0.15.1: energia domu i strzałki sieci

Dom w kWh liczymy jako PV + import + rozładowanie − eksport − ładowanie. Każdy licznik wnosi wszystkie dostępne przyrosty z wybranego okresu kalendarzowego. Nie przecinamy list znaczników czasu różnych źródeł: brak nocnej statystyki PV nie usuwa nocnego poboru z sieci i baterii. Dotyczy to bieżącego dnia i poprzednich dni, tygodni, miesięcy oraz roku. Odczyt początkowy wyszukujemy także w dwóch dobach poprzedzających okres, co pozwala uwzględnić pierwszą poranną produkcję po nocnym wyłączeniu falownika. Jeżeli w tym zakresie nie ma odczytu początkowego, liczymy dostępne późniejsze przyrosty i oznaczamy niepełną historię. Brak całej historii wymaganego źródła pozostawia zużycie domu nieznane. Informację o niepełnym zakresie otwiera ⓘ na obu kartach. Nieśledzone zużycie korzysta z poprawionego zużycia domu.

W sieci **↓ oznacza energię oddaną do sieci, ↑ pobraną z sieci** — kierunki względem tego zasobu, tak jak w baterii. Znak bieżącej mocy pozostaje + pobór, − eksport. Rozliczenia PGE nadal korzystają z odrębnego, rygorystycznego bilansowania godzinowego; poprawka widoku fizycznej energii go nie zmienia.

## Uzupełnianie po przerwach — 0.16.0

Integracja zapisuje parę narastających liczników i czas w trwałych punktach kontrolnych (co 15 s oraz przy prawidłowym zamknięciu integracji). Po restarcie HA, niedostępności źródła albo przerwie pracy punktów kontrolnych HA powyżej 90 s wykrywa powrót poprawnej pary. Nie przyjmuje stanów odtworzonych przez RestoreState ani niedostępnego odczytu jednego kierunku. Stały licznik, np. eksport w nocy, jest poprawny niezależnie od czasu ostatniej zmiany/raportu; sam brak zmiany wartości nie dowodzi przerwy komunikacji. Spadek licznika zatrzymuje uzupełnienie i zgłasza problem; nie staje się ujemnym zużyciem.

Brakująca energia jest rozliczana **raz i szacunkowo**, jako `0,8 × eksport − import`, bez kompensowania całej przerwy 1:1 i bez proporcjonalnego przypisywania jej do godzin. Przykład 8:30–14:50: import 1000→1010 i eksport 500→505 daje **−6 kWh**. Osobno uwzględniamy znane fragmenty godzin przed przerwą i po powrocie. Zatwierdzenie następuje po zamknięciu pierwszej godziny po powrocie i odczytaniu jej granicy; w przykładzie po 15:00, gdy granica pojawi się w Recorder. Przy braku granic wpis oczekuje na dane — nie wymyślamy odczytu początkowego.

W „Rozliczeniu miesięcznym” jest tabela **Uzupełnienia po przerwach**: zakres, import, eksport, szacunkowa zmiana i status. Saldo zawierające szacunek ma oznaczenie ≈; encje mają atrybuty `recovery_estimated` i `recovery_intervals`. Ponowne uruchomienie lub odświeżenie nie dodaje wpisu ponownie. Nakładające się późne koszyki statystyk nie są liczone drugi raz. Jeśli wróci rzeczywista historia wszystkich granic godzin i zgadzają się sumy obu liczników, dokładne rozliczenie zastępuje szacunek. Sam skok w pierwszej statystyce po powrocie nie jest dowodem takiej historii. Przy przerwie wewnątrz jednej godziny jej kompletne, zgodne sumy graniczne wystarczają do dokładnego rozliczenia.

Szacunkowy przyrost przypisujemy przy powrocie odczytów, także po zmianie daty. FIFO i ważność energii nadal obowiązują, a magazyn pozostaje ≥0; brak zapasu pokazuje Niedobór. Przy przekroczeniu daty lub miesiąca oznaczamy niepewność przypisania energii i terminów. Przerwa przecinająca nową fakturę wymaga dokładniejszych odczytów: automatyczne doliczenie mogłoby ponownie uwzględnić energię już objętą saldem faktury, więc saldo pozostaje wtedy nieznane z objaśnieniem.

Mechanizm działa od zapisania pierwszego punktu kontrolnego po tej aktualizacji. Nie rekonstruuje sam dawnych przerw bez zachowanej pary liczników i odczytów granicznych. Kopia JSON zawiera `recovery_cache`; odczyt starszych kopii pozostaje obsługiwany. Nie zapisujemy korekt do źródłowych statystyk HA ani do faktur. To ostrożny szacunek, a nie gwarancja zgodności z rozliczeniem operatora.
