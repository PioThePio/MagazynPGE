# Publikowanie wersji dla HACS — instrukcja dla autora

Użytkownik raz dodaje publiczne repozytorium do HACS. Potem aktualizuje integrację przyciskiem. Nie musi budować paczek, uruchamiać CI ani korzystać ze środowiska chmurowego Codexa.

## Pierwsza publikacja

Repozytorium `PioThePio/MagazynPGE` musi być **publiczne** i zawierać kod. Publiczne udostępnienie wymaga decyzji właściciela; konfiguracja HACS ani zapis szkicu środowiska nie zmieniają widoczności repozytorium i nie wysyłają kodu.

1. Opublikuj przygotowany kod i włącz GitHub Actions. Dodaj opis, np. „Wirtualny magazyn energii PGE dla Home Assistant”, i tematy `home-assistant`, `hacs`, `energy`.
2. Sprawdź wynik workflow **Tests**.
3. Utwórz i wypchnij tag `v0.2.2` wskazujący sprawdzony commit.
4. Workflow **Release** zweryfikuje wersje i tag, wykona testy, zbuduje paczkę i opublikuje GitHub Release. Dopiero udane wydanie jest gotowe do instalacji przez HACS.

Tag wypychaj dopiero, gdy publikacja danego kodu jest zamierzona: workflow automatycznie publikuje po zaliczeniu kontroli. Nie przepisuj opublikowanych tagów. Workflow używa krótkotrwałego `GITHUB_TOKEN` z zapisem tylko w zadaniu publikacji; nie wymaga osobistego tokenu w sekretach repozytorium.

## Kolejne wersje

1. Wprowadź zmianę, testy i uwagi w `docs/RELEASE_NOTES.md`. Opisz ewentualną migrację danych.
2. Podnieś identycznie wersje w `custom_components/pge_storage/manifest.json`, `custom_components/pge_storage/const.py` i `pyproject.toml`, np. do `0.2.2`. Odśwież `uv.lock` po zmianie deklaracji projektu.
3. Wykonaj `uv run --frozen python scripts/check_release.py --tag v0.2.2` i standardowe kontrole projektu.
4. Opublikuj commit i nowy tag. Workflow utworzy sprawdzone wydanie, które HACS zaproponuje jako aktualizację.

Wersja w `const.py` zmienia też URL karty Lovelace, aby przeglądarka pobrała nowy JS po restarcie HA i odświeżeniu strony. Python, JS, tłumaczenia i ikona pochodzą z tego samego taga.

## Pobieranie i dane

HACS używa standardowego katalogu `custom_components/pge_storage` z wydania. Nie ustawiamy `zip_release`: paczka `MagazynPGE-X.Y.Z.zip` zawiera dodatkowo dokumentację i służy alternatywnej instalacji ręcznej. Nie ma drugiego repozytorium karty.

Faktury i rejestr są w `.storage`, poza katalogiem kodu HACS. Nie zmieniaj `entry_id` ani nie usuwaj wpisu przy zwykłej aktualizacji. Zmiana formatu wymaga osobnej migracji i testów odtworzenia.

Lokalnie sprawdzamy strukturę i pola HACS, ikonę, kartę, zgodność wersji, odrzucenie błędnego taga, polecenia testowe i ZIP. To nie dowodzi wykonania GitHub Actions ani instalacji z docelowego HA; te kroki można sprawdzić po publikacji repozytorium.
