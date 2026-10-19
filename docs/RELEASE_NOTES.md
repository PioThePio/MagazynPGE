MagazynPGE 0.8.0 — moc teraz i energia dzisiaj razem; brak mocy oznacza 0 W.

- Diagram i odbiorcy pokazują obie wartości jednocześnie: główna moc W i mniejsze dzisiejsze kWh. Usunięto przełącznik Teraz/Dzisiaj. Akumulator pokazuje SOC, moc i dzisiejsze ładowanie/rozładowanie.
- Każdy brakujący, unknown, unavailable lub niepoprawny odczyt mocy daje 0 W dla tego źródła; pozostałe źródła nadal się sumują. Obie instalacje PV bez odczytu dają 0 W, a dom uwzględnia działającą sieć i baterię. Usunięto blokowanie mocy PV przez brak drugiego pomiaru w Energii. Wartości mocy domu są nieujemne.
- Konfigurator pokazuje dla każdej instalacji PV osobne przypisania kWh/W oraz pochodzenie z Energii. Nie dobiera nieznanych sensorów mocy po nazwie licznika energii.
- Własny sensor zapasu akumulatora jest wyraźnie opcjonalny; podgląd SOC × pojemność pokazuje wynik przed zapisem. Zapas kWh nie blokuje mocy domu.
- Historia kWh, faktury i oryginalne sensory pozostają zachowane. Brakujący odczyt narastającego licznika nie jest zastępowany zerem w rozliczeniu.

Aktualizacja: HACS → 0.8.0 → restart HA → Ctrl+F5. Nowy widok działa na istniejących kartach, a zapisane źródła pozostają zachowane. Ręczne zmiany konfiguracji działają bez restartu.
