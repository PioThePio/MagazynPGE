MagazynPGE 0.11.0 — tabela odbiorców i historia nieśledzonego zużycia.

- Kolumny Nazwa / Moc / Średnia / Energia są wyrównane w tabeli. Kliknięcie nagłówka sortuje, ponowne kliknięcie odwraca kierunek. Usunięte osobne przyciski sortowania. Hierarchia rodziców i podliczników pozostaje zachowana.
- Średnia odbiorców w menu rozwijanym, domyślnie 5 s. Diagram ma własne menu 1/5/10/15 s, domyślnie 10 s. Okno średniej jest niezależne od częstotliwości aktualizacji; nie dodano jeszcze wyzwalania diagramu raportem Solplanet. Encja zużycia domu zachowuje dotychczasowe 15 s.
- Nowe encje: Nieśledzone zużycie (W) i Nieśledzone zużycie dzisiaj (kWh). Kliknięcie wiersza otwiera historię encji mocy. W ma klasę pomiaru, umożliwiającą statystyki długoterminowe; historia zbiera się od aktualizacji przy włączonym Recorder dla tych encji. Energia dzienna pozostaje podpisaną różnicą, nie sztucznym licznikiem narastającym.
- Bez zmiany źródeł, faktur i rozliczeń PGE. Ładowanie baterii i podliczniki są uwzględniane tak jak w dotychczasowym bilansie.

Aktualizacja: HACS → 0.11.0 → restart HA → Ctrl+F5.
