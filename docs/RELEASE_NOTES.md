MagazynPGE 0.17.0 — prosty czas baterii, szczegóły rezerwy i podgląd profilu.

- Jeden czas pod diagramem: „Wystarczy na…” przy rozładowaniu, „Do pełna…” przy ładowaniu. Bez wypisywania minimum SOC na głównym ekranie. Postój/znikoma moc: kreska.
- Kliknięcie baterii lub czasu otwiera szczegóły: energia całkowita, dostępna energia, aktualne minimum SOC, rezerwa i jej dodatkowy teoretyczny czas do 0%. Minimum pochodzi z encji, bez sztywnego 20%. Okno nie znika przy odświeżaniu.
- Średnia mocy do czasu startuje z dostępnej historii Recorder. Bez historii zaczyna od krótszego okna po około 30 s i stopniowo dochodzi do wybranych 1/5/15 min. Widać faktycznie używaną długość średniej.
- Profil ładowania w ustawieniach zaawansowanych baterii: wykres W według SOC i tabela obserwacji. Brakujące zakresy nie są zerami; odróżniamy zakresy gotowe (≥3 obserwacje) od niepełnych.
- ⓘ w konfiguratorze pokazuje dymek po najechaniu, bez rozwijacza. Informacyjne rozwijacze z głównego diagramu i listy odbiorców usunięto.
- Odczyty historii kończą się przed zamknięciem bazy Recorder podczas zatrzymywania HA.

Aktualizacja: HACS → 0.17.0 → restart HA → Ctrl+F5. Wybrane źródła, minimum SOC, pojemność i profil pozostają zachowane. Nie trzeba ponownie konfigurować baterii. Rezerwa jest oszacowaniem podczas rozładowania, nie obietnicą energii dostępnej poniżej limitu ESS.

Weryfikacja: 184 testy Python i 33 testy DOM; rzeczywisty Recorder oraz Chromium na komputerze i telefonie, w tym aktualizacje otwartego okna i zamykanie Escape.
