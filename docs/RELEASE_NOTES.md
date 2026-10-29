MagazynPGE 0.16.0 — trwałe, szacunkowe uzupełnienia po przerwach HA i liczników.

Po powrocie poprawnej pary liczników brakujące przyrosty zostają rozliczone raz: eksport ×0,8 − import. Import 10 kWh i eksport 5 kWh dają −6 kWh. Nie rozkładamy przerwy na wymyślone godziny. Znane fragmenty godzin na brzegach są uwzględnione osobno. Zapis jest zatwierdzany po zamknięciu pierwszej godziny po powrocie, gdy dostępne są jej granice. Brak granic pozostawia wpis oczekujący.

Punkty kontrolne przetrwają restart. Ponowne odświeżenie nie dolicza energii drugi raz, także gdy po powrocie pojawi się spóźniony koszyk statystyk. Rzeczywista historia godzin zastępuje szacunek po potwierdzeniu granic i zgodności sum obu liczników. Przywrócenie jednego kierunku nie wystarcza; spadek licznika zatrzymuje automatyczne uzupełnienie.

Tabela „Uzupełnienia po przerwach” w rozliczeniu miesięcznym pokazuje zakresy, przyrosty, zmianę magazynu i status. Saldo ze szacunkiem ma ≈; encje udostępniają atrybuty jakości. FIFO, wygaśnięcia, magazyn ≥0 i Niedobór nadal działają. Przekroczenie daty/miesiąca jest oznaczone jako niepewne. Przerwa przecinająca fakturę wymaga dokładniejszych danych, aby nie podwoić rozliczonej energii.

Aktualizacja: HACS → 0.16.0 → restart HA → Ctrl+F5. Mechanizm jest automatyczny dla skonfigurowanych liczników PGE, bez nowych ustawień. Faktury i źródła pozostają zachowane. Zabezpieczenie zaczyna działać od zapisania pierwszego punktu kontrolnego; nie odtwarza dawnych przerw bez odczytów. Wynik szacunkowy może różnić się od faktury operatora.

Weryfikacja: zestaw 179 testów Python, 30 testów interfejsu, Ruff, składnia JS i metadane wydania.
