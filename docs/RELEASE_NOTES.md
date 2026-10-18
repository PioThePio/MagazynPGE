MagazynPGE 0.6.0 — automatyczne źródła z panelu Energia i obliczanie domu.

- Automatyczne pobranie źródeł sieci, PV, akumulatora i odbiorców z konfiguracji Energii HA. Dotychczasowe ręczne wybory zachowane. Przycisk „Wczytaj z panelu Energia” umożliwia ponowny import; każdą encję można zmienić ręcznie.
- Osobna encja domu nie jest wymagana. „Oblicz z bilansu”: PV + pobór sieci + rozładowanie − oddanie sieci − ładowanie. Osobno dla W i kWh. Ręczna encja domu ma pierwszeństwo.
- Wiele źródeł PV, statystyki zewnętrzne, kierunki mocy i pojemność akumulatora z panelu Energia. Dzisiejsza energia z godzinowych sum Recorder obsługuje resetowane liczniki. Karta pokazuje czas kompletnego odczytu „do HH:mm”. Braki pozostają puste.
- Konfiguracja natywnej Energii, źródłowe sensory, zapisane faktury i rozliczeniowa para PGE pozostają zachowane. Wszystkie obliczone wartości są nadal dostępne jako samodzielne encje.

Aktualizacja: HACS → 0.6.0 → restart HA → Ctrl+F5. Restart ładuje nowy kod Pythona. Po tej aktualizacji źródła pobiorą się automatycznie; pola domu pozostaw jako „Oblicz z bilansu”. Ponowny import i ręczne zmiany źródeł działają bez restartu.
