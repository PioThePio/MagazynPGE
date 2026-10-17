# Instalacja raz, potem aktualizacje przyciskiem

MagazynPGE działa lokalnie w Home Assistant. HACS pobiera jedynie kod z GitHuba przy instalacji i aktualizacji. Nie potrzebujesz serwera w chmurze, konta PGE ani działającego Codexa.

Instrukcja dotyczy Twojego HA OS z Core 2026.10.0 i istniejącym HACS. Zacznie działać po opublikowaniu kodu i pierwszego wydania w **publicznym** repozytorium `PioThePio/MagazynPGE`. Sam ZIP w środowisku roboczym nie udostępnia integracji w HACS.

## Pierwsza instalacja

1. Otwórz **HACS → ⋮ → Repozytoria niestandardowe / Custom repositories**.
2. Wklej `https://github.com/PioThePio/MagazynPGE`, wybierz typ **Integracja / Integration** i kliknij **Dodaj**.
3. Wyszukaj **Magazyn energii PGE**, otwórz i kliknij **Pobierz / Download**. Wybierz stabilne wydanie, np. `v0.2.1`.
4. Uruchom ponownie HA.
5. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację → Magazyn energii PGE**.
6. Wybierz parę SDM640: import **„630 E import”**, eksport **„630 E export”**. Alternatywnie wybierz oba kanały Victrona: `energymeter_consumption` i `energymeter_feed_in`. Nie wybieraj gotowego bilansu ani nie sumuj obu zestawów.
7. Na dashboardzie wybierz **Edytuj → Dodaj kartę**, wyszukaj **Magazyn energii PGE** i zapisz kartę. Jeżeli jeszcze jej nie widać, odśwież przeglądarkę po restarcie HA. Możesz też użyć ręcznej konfiguracji karty:

   ```yaml
   type: custom:pge-storage-card
   title: Wirtualny magazyn PGE
   ```

8. Dodaj datę początkową i rozliczenia na karcie zgodnie z [README](../README.md).

Karta jest częścią integracji. Nie wymaga osobnej instalacji frontendowej w HACS. W standardowym trybie zasobów HA integracja sama dodaje i aktualizuje moduł Lovelace.

Jeżeli świadomie ustawiono `lovelace.resource_mode: yaml`, zasoby pozostają pod kontrolą użytkownika. W istniejącej sekcji `lovelace.resources` w `configuration.yaml` dodaj (lub zaktualizuj) jeden wpis:

```yaml
lovelace:
  resource_mode: yaml
  resources:
    - url: /pge_storage/pge-storage-card.js?v=0.2.1
      type: module
```

Scal go z istniejącą konfiguracją, zachowując pozostałe zasoby; nie dodawaj drugiej sekcji `lovelace`. Po aktualizacji zmień numer wersji URL, uruchom ponownie HA i odśwież stronę. Sam dashboard zapisany w YAML nie wymaga tego kroku — dotyczy on wyłącznie zarządzania **zasobami** w YAML.

## Następne wersje

1. W **Ustawienia → System → Aktualizacje** albo w HACS otwórz aktualizację **Magazyn energii PGE**.
2. Przeczytaj uwagi do wydania, wykonaj backup / pobierz kopię rejestru JSON i kliknij **Aktualizuj**.
3. Zrestartuj HA i odśwież dashboard.

Bez kopiowania plików, ponownego wybierania liczników i ponownego wpisywania faktur. HACS sprawdza wydania okresowo; można też odświeżyć informacje o repozytorium. Samo **Update information** odświeża informacje; kod instaluje **Download / Aktualizuj**.

Rejestr znajduje się w `/config/.storage/pge_storage.<entry_id>`, poza katalogiem kodu zarządzanym przez HACS. **Nie usuwaj wpisu integracji w „Urządzenia i usługi” przy aktualizacji** — usunięcie wpisu usuwa jego rejestr. Wydanie zmieniające format danych musi zawierać instrukcję migracji.

## Przejście z ręcznej instalacji

Jeżeli wgrałeś **0.2** ręcznie, pobierz JSON i zrób backup. Dodaj repozytorium w HACS, pobierz tę samą lub nowszą wersję i zrestartuj HA. Zachowaj istniejący wpis integracji. HACS zastąpi katalog kodu; własne zmiany w tych plikach zachowaj wcześniej w kopii. Dla prototypu **0.1** obowiązują osobne kroki przejścia z README.

## Gdy HACS nie znajduje projektu

Repozytorium musi być publiczne i zawierać `hacs.json` oraz `custom_components/pge_storage`. Potrzebne jest stabilne **GitHub Release**, nie sam tag: domyślna gałąź jest ukryta, aby nie oferować zmian roboczych. Minimalny Core to 2026.10.0. HACS potrzebuje działającego dostępu do GitHuba; tokenów nie przekazuj przez czat.

Oficjalne instrukcje: [repozytorium niestandardowe](https://www.hacs.xyz/docs/faq/custom_repositories/), [aktualizacje](https://www.hacs.xyz/docs/use/update/), [wymagania integracji](https://www.hacs.xyz/docs/publish/integration/).
