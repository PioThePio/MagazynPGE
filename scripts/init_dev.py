"""Create an isolated local HA config. Never point this at your production config."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CONFIGURATION = """# Isolated MagazynPGE development instance — no production HA data.
homeassistant:
  name: Magazyn PGE — development
  time_zone: Europe/Warsaw
  country: PL
  latitude: 52.23
  longitude: 21.01
  elevation: 100
http:
  server_host: 127.0.0.1
  server_port: 8123
frontend:
recorder:
  purge_keep_days: 30
input_number:
  pge_demo_import_total:
    name: Energia importowana — demonstracja
    min: 0
    max: 1000000
    step: 0.1
    initial: 7410
    unit_of_measurement: kWh
    mode: box
  pge_demo_export_total:
    name: Energia eksportowana — demonstracja
    min: 0
    max: 1000000
    step: 0.1
    initial: 10000
    unit_of_measurement: kWh
    mode: box
template:
  - sensor:
      - name: PGE demo import total
        unique_id: pge_demo_import_total
        state: "{{ states('input_number.pge_demo_import_total') }}"
        unit_of_measurement: kWh
        device_class: energy
        state_class: total_increasing
      - name: PGE demo export total
        unique_id: pge_demo_export_total
        state: "{{ states('input_number.pge_demo_export_total') }}"
        unit_of_measurement: kWh
        device_class: energy
        state_class: total_increasing
lovelace:
  dashboards:
    pge-storage:
      mode: yaml
      title: Magazyn PGE
      icon: mdi:transmission-tower
      show_in_sidebar: true
      require_admin: true
      filename: pge-dashboard.yaml
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / ".ha-dev")
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory == ROOT or directory == Path("/config"):
        parser.error(
            "Użyj oddzielnego katalogu testowego, nie repozytorium ani /config."
        )
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / "configuration.yaml"
    if not config.exists():
        config.write_text(CONFIGURATION, encoding="utf-8")
    else:
        print("Zachowano istniejący configuration.yaml.")
    for name, target in {
        "custom_components": ROOT / "custom_components",
        "pge-dashboard.yaml": ROOT / "dashboards" / "pge.yaml",
    }.items():
        link = directory / name
        if link.is_symlink() and link.resolve() == target:
            continue
        if link.exists() or link.is_symlink():
            raise SystemExit(f"Nie nadpisuję istniejącej ścieżki: {link}")
        link.symlink_to(target, target_is_directory=target.is_dir())
    print(f"Przygotowano: {directory}")


if __name__ == "__main__":
    main()
