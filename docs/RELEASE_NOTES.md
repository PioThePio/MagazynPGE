MagazynPGE 0.18.0 — osobne moduły dashboardu i szczegóły energii.

- Rozdzielono sterowanie zakresem, diagram i czas baterii na niezależne karty Lovelace. `sync_group` łączy zakres i średnią wybranych kart; istniejące karty i ustawienia są zachowane.
- Diagram ma większe, równo rozstawione okręgi, węższą kolumnę instalacji PV i animację wyłącznie przy przepływie energii. Animację można wyłączyć; uwzględniane jest `prefers-reduced-motion`.
- Bilans bieżącej godziny pokazuje P−E do 0,1 kWh. Kliknięcie otwiera słupki godzinowe: pobór ponad osią, eksport poniżej, bieżąca godzina wyróżniona. Szczegóły pokazują dokładny wynik i zmianę magazynu po opuście.
- Graficzne szczegóły akumulatora pokazują rzeczywistą rezerwę do wybranego minimum SOC, energię dostępną i wolną pojemność. Nowa encja rezerwy otwiera natywną historię HA, podobnie jak istniejące encje energii baterii.
- Podczas ładowania czas pracy dostępnej energii i rezerwy wykorzystuje ważoną czasem moc z okresów rozładowania z ostatnich 24 godzin. Braki odczytów, ładowanie i postój nie są liczone jako 0 W.
- Energia odbiorców może pojawiać się wiersz po wierszu. Odczyt roku opiera się na dziennych statystykach HA i dokładnych granicach godzin, z zachowaniem częściowej historii i braków danych.

Model rozliczeń godzinowych, FIFO, odzyskiwanie po przerwach, identyfikatory dotychczasowych encji i konfiguracja źródeł pozostają zachowane. Aktualizacja: HACS → 0.18.0 → restart HA → odświeżenie dashboardu.
