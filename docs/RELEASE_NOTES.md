MagazynPGE 0.15.1 — poprawka zaniżonej energii domu i strzałek sieci.

Usunięto błąd polegający na ograniczeniu zużycia domu do znaczników czasu wspólnych dla PV, sieci i baterii. Nocna przerwa w statystykach falownika nie usuwa już poprawnie zarejestrowanego nocnego poboru. Każdy licznik wnosi dostępne przyrosty z wybranego dnia/tygodnia/miesiąca/roku. Poprawka obejmuje bieżący dzień i zamknięte okresy, diagram, odbiorców i nieśledzone zużycie. Odczyt początkowy jest wyszukiwany także w dwóch poprzednich dobach, aby zachować pierwszy poranny przyrost PV. Niepełna historia ma objaśnienie pod ⓘ; brak całej historii skonfigurowanego źródła pozostawia wynik nieznany.

W kółku Sieć: ↓ oddano do sieci, ↑ pobrano z sieci. Bieżąca moc nadal ma znak + pobór / − oddawanie. Rozliczenia godzinowe PGE i faktury pozostają zachowane.

Test regresyjny na natywnym Recorder, z falownikiem bez nocnych statystyk, potwierdza 17,32 kWh zarówno dla dnia bieżącego, jak i zamkniętego. Wynik porównano niezależnie z natywnymi przyrostami HA używanymi przez panel Energia. Dodatkowe testy obejmują rozłączne czasy raportowania, brak całego źródła, podpowiedź niepełnego zakresu i kierunki strzałek.

Aktualizacja: HACS → 0.15.1 → restart HA → Ctrl+F5. Nie trzeba ponownie wpisywać konfiguracji, faktur ani dni — energia okresów zostanie odczytana ponownie.

Weryfikacja: 165 testów Python i 29 testów DOM, Ruff, składnia JS oraz zgodność metadanych wydania.
