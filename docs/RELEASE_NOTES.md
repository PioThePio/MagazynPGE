MagazynPGE 0.2.0 — pierwsze wydanie z obsługą HACS.

- Wybór oddzielnych liczników importu i eksportu SDM640 albo Victrona.
- Historia rozliczeń PGE, saldo z faktur, korekty i trwały rejestr.
- Karta Lovelace z edycją, tabelą, wykresem i kopiami JSON.
- Integracja i jej karta są instalowane oraz aktualizowane razem przez HACS.

Wymagany Home Assistant Core 2026.10.0 lub nowszy; testy wykonano na 2026.10.0 i frontendzie 20260930.2. Po instalacji lub aktualizacji uruchom ponownie HA. Samo minimum wersji HACS nie oznacza przetestowania wszystkich przyszłych wersji Core.

Dodaj repozytorium `PioThePio/MagazynPGE` w HACS jako **Integracja**. Po pobraniu i restarcie dodaj **Magazyn energii PGE** w ustawieniach integracji HA. Instrukcja instalacji i aktualizacji znajduje się w README oraz `docs/HACS.md`.

Jeżeli używałeś prototypu 0.1, zapoznaj się z sekcją przejścia w README przed aktualizacją: jego próbki nie zawierały dwóch liczników i nie mogą być automatycznie zamienione na nowy format.
