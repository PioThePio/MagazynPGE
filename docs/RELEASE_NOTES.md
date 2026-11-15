MagazynPGE 0.18.1 — poprawki bilansu godzin i akumulatora.

- Wybór godziny pozostaje widoczny podczas odświeżania, a zmiana magazynu po opuście jest zaokrąglana do 0,1 kWh.
- Godziny potwierdzone odczytami Recorder na granicach godzin mogą zastąpić oczekujący blok po restarcie, także gdy brakuje granic w lokalnym cache. Nieznane okresy pozostają oznaczone jako niepewne.
- Nowa osobna karta `custom:pge-battery-graphic-card` i wspólny widok szczegółów pokazują podział energii, moc, czasy oraz animowany kierunek. Wartości prowadzą do encji HA.
- Komunikat o luce godzinowej usunięto z głównego diagramu; informacje o odzyskiwaniu pozostają w historii.

Aktualizacja: HACS → 0.18.1 → restart HA → odświeżenie dashboardu.
