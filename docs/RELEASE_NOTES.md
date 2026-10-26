Magazyn PGE rozlicza teraz każdą godzinę zegarową osobno: kompensacja poboru i eksportu 1:1, następnie opust 0,8 od nadwyżki eksportu. FIFO uwzględnia ważność partii, a zamknięte godziny są utrwalane w Store i kopii JSON formatu 5.

- Dwie encje bieżącej godziny: bilans przed opustem i wpływ na magazyn, z jakością i czasem danych.
- Braki historii rozliczeniowej pozostają nieznane; brak mocy opcjonalnego urządzenia nadal oznacza 0 W.
- Diagram odświeżany wspólnie raportem wybranego PV, z rytmem zastępczym 10 s i niezależną średnią.
- Magazyn PGE pod siecią, bez fizycznej strzałki do domu.
- Zachowane faktury i identyfikatory encji. Stare profile surowego importu wymagają ponownego odczytu historii lub zapisania założeń.

Aktualizacja: HACS → aktualizuj → restart HA → Ctrl+F5. Restart jest konieczny dla nowego silnika Python i rejestracji nowych encji. Automatyzacje i bufory sterowania nie są częścią wydania.
