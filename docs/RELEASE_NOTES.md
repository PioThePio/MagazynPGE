MagazynPGE 0.17.1 — diagnostyka częstotliwości raportowania odbiorców.

- Najedź na nazwę odbiorcy w karcie „Odbiorcy w domu”: typowy odstęp (mediana), średni odstęp, najdłuższa przerwa między raportami, liczba raportów z ostatnich 5 minut oraz wiek ostatniego raportu.
- Liczymy zarówno zmiany stanu, jak i identyczne raporty encji HA. Samo odświeżanie karty nie jest raportem.
- Diagnostyka zbiera się na żywo od uruchomienia integracji; przy mniej niż dwóch raportach pokazuje „Ustalanie częstotliwości”. Po dłuższej przerwie stare raporty wypadają z okna.
- To częstotliwość zapisów encji przez integrację, nie dowód częstotliwości wewnętrznych pomiarów urządzenia. Nie zmieniamy średnich, mocy, energii ani rozliczeń PGE.

- Usunięto pętlę unieważniania historii: ponowne odczytanie tych samych danych nie zmienia wersji rozliczeń i nie przerywa ładowania dni.

Aktualizacja: HACS → 0.17.1 → restart HA → Ctrl+F5. Ustawienia pozostają zachowane. Do diagnostyki potrzebna jest skonfigurowana encja mocy odbiorcy.
