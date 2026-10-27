MagazynPGE 0.13.1 — zamknięte saldo godzinowe, odświeżanie 3 s i estymacja baterii.

- Magazyn i niedobór zmieniają się dopiero po zamknięciu godziny z kompletem danych. Magazyn minimum 0 kWh, niedobór pozostaje osobno.
- Mała bieżąca godzina między Siecią a Domem, szczegóły po kliknięciu, możliwość ukrycia oraz osobna karta. Nowe znaki P−E: plus pobór, minus eksport (odwrócone względem 0.12.0). Historia encji nie jest przepisywana.
- Diagram co 3 s: domyślnie wyrównane pomiary z opóźnieniem 12 s, opcjonalnie najnowsze odczyty. Średnie niezależne. Pierwsze 27 s zbiera historię.
- Sieć pokazuje Pobrano/Oddano bez opustu; PGE rozliczenie po kompensacji godzinowej. Kolorowe obwódki pokazują szacowane udziały mocy. Słońce nad domem, instalacje po lewej z ustawianą kolejnością.
- Czas baterii do 100% i do wybranego minimum SOC; średnie 1/5/15 min. Wymaga SOC, rzeczywistej mocy i pojemności. Przy mocy do 25 W brak estymacji. Opcjonalny profil uczony z ograniczeń BMS i scenariusz dwóch zgodnych prognoz energii PV/domu.
- Nowe encje potrącenia opustu od faktury i dzisiaj oraz karta dla wybranego okresu. Dwie encje czasu baterii.
- Całkowite jednostki mocy na dashboardzie; rodzice odbiorców bez strzałek, dzieci zachowują wcięcia. Usunięta etykieta Dostępna historia.

Aktualizacja: HACS → 0.13.1 → restart HA → Ctrl+F5. Faktury, partie i identyfikatory encji pozostają zachowane. W konfiguratorze źródeł uzupełnij pojemność i minimum SOC, jeśli chcesz czas rozładowania. Nowe karty dodasz w natywnym edytorze HA; istniejący dashboard nie jest nadpisywany.

Profil baterii jest również usuwany z zapisu na dysku przy zmianie źródeł baterii lub pojemności. Zmiana kolejności PV i średniej nie usuwa nauki.
