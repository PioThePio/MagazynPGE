MagazynPGE 0.3.0 — czytelny magazyn, dzienne przepływy i planowanie zimy.

- MAGAZYN pokazuje energię do odbioru po opuście. Obok jest odpowiednik pozostałej energii wprowadzonej przed opustem. Wszędzie na karcie jedno miejsce po przecinku; dane zachowują pełną precyzję.
- Dzienne odczyty: import, część pokryta magazynem, eksport, dodane kWh po opuście, przepływ netto i saldo; dzisiaj jako dzień niepełny. Brak danych pozostaje nieznany. Znalezione zakończone dni są archiwizowane we własnym Store.
- Partie z faktury, FIFO i terminy ważności z domyślną regułą 12 miesięcy od końca miesiąca wprowadzenia. Osobne zużycie i doładowanie, trwałe miesięczne odczyty.
- Profil miesięczny ręczny albo pobrany z kompletnych statystyk HA. Scenariusz do wybranej daty (domyślnie 31 marca), saldo, pierwszy niedobór, wygaśnięcia, wykres i projekcyjne wskazania obu liczników. Brak założeń nie jest zastępowany optymistyczną prognozą z października.
- Najważniejsze salda faktur są na początku tabeli; techniczne odczyty w szczegółach. Dostarczany dashboard używa pełnej szerokości Panel.

Aktualizacja z 0.2: HACS → Aktualizuj do 0.3.0 → restart HA → Ctrl+F5. Zachowaj wpis integracji i rozliczenia. Eksport JSON wersji 3 obejmuje plan i archiwa; stare kopie wersji 2 są nadal odczytywane. Przed aktualizacją i ewentualnym powrotem do starszej wersji zachowaj kopię.

Na karcie rozwiń „Ustaw prognozę i partie z faktury”, wczytaj/wpisz partie z ostatniej faktury, pobierz profil z HA, uzupełnij brakujące miesiące i zapisz plan. Opis założeń, importu partii i typów salda: README. Daty i prognoza są modelem planistycznym, a nie potwierdzeniem salda PGE.
