MagazynPGE 0.7.0 — osobne karty HA, czytelne źródła PV i ustawienia Victrona.

- „Utwórz dashboard z osobnych kart” tworzy natywny dashboard Lovelace z ośmioma niezależnymi kartami. Każdą przesuniesz i edytujesz ołówkiem HA. Ponowne wywołanie zachowuje Twoje zmiany i inne dashboardy.
- Nowa osobna karta „Odbiorcy w domu”. Schemat przepływów pokazuje wyłącznie PV, sieć, dom, akumulator i magazyn PGE. Dotychczasowy zestaw modułów reaguje na szerokość karty, także na szerokim ekranie; koła i podpisy nie nachodzą na siebie.
- Wszystkie PV są jawnie widoczne jako wybrane źródła. Brakujący sensor importowany z Energii nie blokuje zapisu, a historyczne statystyki pozostają dostępne. Brak historii pozostaje brakiem danych. Częściowa moc PV nie udaje sumy całej instalacji.
- Prosty wybór pomiaru mocy: jeden sensor +/− albo dwa kierunki. Opisy kWh, mocy, SOC, energii w akumulatorze i pojemności. Naprawiony import nazw pomocniczych sensorów mocy i pierwszeństwa power_config Energii.
- Konfiguracja źródłowej Energii, sensory i faktury pozostają zachowane.

Aktualizacja: HACS → 0.7.0 → restart HA → Ctrl+F5. Następnie „Utwórz dashboard z osobnych kart” i „Otwórz dashboard”. Źródła energii → Wczytaj z panelu Energia → Zapisz źródła. Dalsze zmiany ustawień działają bez restartu.
