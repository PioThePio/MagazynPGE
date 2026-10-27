MagazynPGE 0.14.0 — automatyczne porządkowanie dashboardu i widoczne strzałki.

Po restarcie integracja zamienia starą zbiorczą kartę PGE na osobne moduły. Jeśli w tym samym widoku jest już osobny diagram, zachowuje go zamiast tworzyć drugi. Pozostałe karty i ich ustawienia pozostają na miejscu. Przed zmianą zapisuje oryginalny układ w osobnej kopii HA Store. Operacja jest powtarzalna i nie nadpisuje późniejszych edycji, gdy karta zbiorcza została już usunięta. W ustawieniach jest też przycisk „Uporządkuj obecny dashboard”. Dashboardy YAML i niejednoznaczne karty przy wielu integracjach pozostają bez zmian.

Wskaźnik bieżącej godziny przeniesiony nad linię Sieć–Dom, tak aby nie zasłaniał kierunku przepływu. Strzałki są wyraźniejsze. Kliknięcie nadal otwiera szczegóły godziny.

Przy prawidłowym SOC i brakującej pojemności komunikat baterii wskazuje konkretnie brak pojemności, zamiast sugerować błąd SOC.

Aktualizacja: HACS → 0.14.0 → restart HA → Ctrl+F5. Nie dodawaj ręcznie kolejnych kopii kart. Faktury, partie i źródła pomiarowe pozostają zachowane.
