MagazynPGE 0.9.0 — okresy energii, foldery odbiorców i nowy diagram przepływów.

- Suma W i kWh domu, śledzone oraz nieśledzone zużycie. Urządzenia mają jedną cyfrę po przecinku. Relacja nadrzędna z Energii tworzy rozwijane foldery, np. AC / AC-Dół / AC-Góra; sumy nie dublują podliczników. Stare zaimportowane konfiguracje otrzymują hierarchię przy zachowaniu ręcznych źródeł.
- Wybór dnia, tygodnia, miesiąca i roku oraz nawigacja dat strzałkami i kalendarzem. W pozostają bieżące, kWh odnoszą się do wybranego okresu. Statystyki Recorder obsługują resetowane liczniki, konwersję Wh/kWh, zewnętrzne statystyki i zmianę czasu.
- Czytelniejsze koła: moc główna, energia pod spodem, jedna podpisana moc sieci, kierunkowe strzałki. Suma PV i oddzielne moce instalacji. PGE ma zapas, wpłatę energii po opuście i pobranie z magazynu. Akumulator pokazuje moc, mały SOC oraz energię ładowania i rozładowania.
- Pojemność baterii można podać w kWh albo w Ah i napięciu nominalnym. Bez napięcia nie przeliczamy samych Ah. Własna encja zapasu kWh jest opcjonalna; podgląd oblicza zapas z SOC i pojemności.
- Zachowane faktury i źródła. Brak mocy nadal wnosi 0 W; brak historycznej energii pozostaje brakiem danych.

Aktualizacja: HACS → 0.9.0 → restart HA → Ctrl+F5. Karty aktualizują się w istniejących dashboardach. W razie ręcznych źródeł relacje nadrzędne możesz wybrać w konfiguratorze. Kolejne zmiany ustawień działają bez restartu.
