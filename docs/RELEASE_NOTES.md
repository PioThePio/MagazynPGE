MagazynPGE 0.18.2 — poprawki widoku akumulatora.

- Wartości energii w wąskich częściach baterii mogą zawijać jednostkę do kolejnego wiersza. Końcówka jest oddzielona kreską i pozostaje poza skalą 100%.
- Trzy rzędy animowanych znaczników pokazują kierunek przy granicy SOC; kolumny odpowiadają mocy, a znaczniki są po stronie wolnego miejsca przy ładowaniu i po stronie zgromadzonej energii przy rozładowaniu.
- Przywrócono podsumowanie energii i podstawy wyliczenia czasu pod szczegółami baterii. Jest też dostępne jako osobna karta `custom:pge-battery-summary-card`.

Aktualizacja: HACS → 0.18.2 → restart HA → odświeżenie dashboardu.
