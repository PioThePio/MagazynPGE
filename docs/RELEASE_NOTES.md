MagazynPGE 0.4.0 — miesiące rozwijane do dni i prosta projekcja obecnego zapasu.

- Wszystkie wyniki na karcie i sugerowane wyświetlanie sensorów: pełne kWh. Obliczenia i zapis pozostają dokładne.
- Wpłaty i pobory: klikany miesiąc, pod nim pięć kolumn — data, wprowadzono po opuście, pobrano, różnica i saldo na koniec dnia. Po wczytaniu nagłówek zawiera sumy miesiąca. Usunięto techniczne komunikaty o imporcie niepokrytym magazynem.
- Projekcja do następnego rozliczenia: miesiąc, pobór taki jak rok wcześniej i pozostałe saldo. Bez przyszłego eksportu i wzrostu zużycia; znane terminy ważności są uwzględnione. Brak historii daje puste saldo od pierwszej luki, zamiast zerowego zużycia.
- Dawny profil zastępuje „Pobór z sieci w poprzednim roku”. Historia potrzebuje tylko statystyk importu; brak eksportu nie blokuje miesiąca. Przy wartościach widnieje miesiąc źródłowy. Domyślna data końcowa to sześć miesięcy po ostatniej fakturze, edytowalna.

Wymagany restart HA: zmieniły się obliczenia Python i odczyt historii, nie tylko wygląd karty.
Aktualizacja: HACS → Aktualizuj do 0.4.0 → restart HA → Ctrl+F5. Zachowaj integrację, faktury i partie. W ustawieniach karty kliknij „Wczytaj pobór z historii HA”, następnie „Zapisz plan i przelicz prognozę”, aby odświeżyć historyczne wartości i ich daty. Jeśli nadal są dostępne tylko letnie miesiące, HA nie ma kompletnych statystyk zimowego poboru — nie tworzymy ich z domysłów.
