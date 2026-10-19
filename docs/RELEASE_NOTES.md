MagazynPGE 0.10.0 — średnie mocy, sortowanie odbiorców i dostępna historia energii.

- Diagram przepływów i encja zużycia domu używają wspólnego okna 15 s, ważonego czasem. To ogranicza skoki przy różnych odstępach raportowania PV i sieci. Przez pierwsze 15 s po uruchomieniu lub zmianie źródeł pokazywana jest moc chwilowa. Brak odczytu mocy nadal wnosi 0 W, również przy wyłączonym nocą falowniku.
- Odbiorcy pokazują moc chwilową, średnią 1/5/10/15 s i energię wybranego okresu. Sortowanie: nazwa, moc, średnia, energia. Nieśledzone uczestniczy w tym samym sortowaniu. Hierarchia urządzeń pozostaje zachowana; pozycje zmieniają się nie częściej niż co 5 s (dla średniej 10/15 s — co 10/15 s). Średnie odświeżają się co sekundę oraz przy zmianach źródeł; historia energii co 5 minut.
- Rok, miesiąc, tydzień i dzień wykorzystują dostępne sumy statystyk, nawet gdy historia zaczyna się w środku roku. Nie wymagamy zapisu od 1 stycznia. Suma obejmuje obserwowane odczyty; brakująca część jest oznaczona jako dostępna historia. Bilans domu wykorzystuje wspólne granice czasowe składników i odejmuje ładowanie baterii.
- Dzisiejsze kWh uwzględniają statystyki pięciominutowe HA. Energia nie jest całkowana z wygładzonej mocy. Faktury, FIFO i rozliczenia PGE pozostają niezależne od okien mocy i częściowych podsumowań.
- Dni w tabeli od najnowszego; wykres zachowuje chronologię. Usunięta dolna legenda diagramu.

Aktualizacja: HACS → 0.10.0 → restart HA → Ctrl+F5. Faktury i konfiguracja pozostają zapisane.
