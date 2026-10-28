MagazynPGE 0.15.0 — wspólne średnie mocy, źródła Energii i pojemność BMS.

- Diagram i odbiorcy korzystają z tych samych pomiarów i wspólnego odświeżania co 3 s. Przy tym samym oknie moc domu jest identyczna. Menu: 1/5/10/15 s oraz 1/5/15/30 min. Długie średnie korzystają z historii Recorder; niepełne pokrycie jest oznaczone.
- Nowi odbiorcy Energii są dopisywani automatycznie przy starcie i co 5 min. Ręczne nazwy, źródła i hierarchia pozostają zachowane; jawnie usunięci odbiorcy nie wracają. Konflikty wymagają sprawdzenia, nie usuwają konfiguracji.
- Własne nazwy instalacji PV, zgodny raport źródeł W, dłuższe podpowiedzi pod ⓘ, ustawienia zaawansowane i komunikat niezapisanych zmian.
- Pojemność z Capacity BMS, zastępczo Installed capacity. Ah przeliczamy napięciem nominalnym; dla SIMPO 5000: 51,2 V. Osobne encje pełnej pojemności i energii dostępnej ponad minimum SOC. Ręczne wartości pozostają zapisane.
- Opcjonalny profil ograniczenia ładowania korzysta z istniejącej historii do 7 dni. Pamięć profilu zachowuje starsze obserwacje po usunięciu historii przez Recorder. Widoczne pokrycie i przycisk przebudowy. Wymagane są SOC, Power, dopuszczalny prąd ładowania BMS i DC bus voltage; brak historii nie jest zerem.
- W sieci wracają strzałki ↓/↑ fizycznego importu/eksportu. Magazyn PGE nadal rozlicza zamknięte godziny i opust 0,8.

Aktualizacja: HACS → 0.15.0 → restart HA → Ctrl+F5. Potem w konfiguracji baterii można wybrać Capacity, Installed capacity i napięcie nominalne 51,2 V, a następnie Zapisz źródła. Zmiana ustawień nie wymaga restartu. Faktury, partie i dotychczasowe źródła pozostają zachowane; nie dodawaj ponownie kart.

Weryfikacja lokalna: 161 testów Python, 28 testów DOM, kontrola składni JS, Ruff i zgodności metadanych wydania. Testy natywnego HA obejmują odczyt historii, długie średnie, odbudowę profilu, cache i zachowanie po usunięciu historii. Brak dostępu do instalacji użytkownika — rzeczywiste odczyty wymagają jego testów.
