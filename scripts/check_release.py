"""Fail before publishing if the tag, application and HACS metadata disagree."""

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Expected GitHub release tag, e.g. v0.2.0")
    args = parser.parse_args()
    integration = ROOT / "custom_components" / "pge_storage"
    manifest = json.loads((integration / "manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    constants = ast.parse((integration / "const.py").read_text())
    version = next(
        ast.literal_eval(node.value)
        for node in constants.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "VERSION"
            for target in node.targets
        )
    )
    failures = []
    if manifest["version"] != version or project["version"] != version:
        failures.append(
            "Wersje manifest.json, const.py i pyproject.toml muszą być identyczne."
        )
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        failures.append("Wydanie musi mieć wersję stabilną X.Y.Z.")
    if args.tag is not None and args.tag != f"v{version}":
        failures.append(f"Tag musi wynosić v{version}, otrzymano {args.tag!r}.")
    if (
        not {
            "domain",
            "documentation",
            "issue_tracker",
            "codeowners",
            "name",
            "version",
        }
        <= manifest.keys()
    ):
        failures.append("Manifest nie zawiera wymaganych pól HACS.")
    if hacs.get("name") != manifest["name"] or hacs.get("homeassistant") != "2026.10.0":
        failures.append("Nieprawidłowa nazwa HACS lub minimalna wersja HA.")
    if (
        hacs.get("zip_release")
        or hacs.get("content_in_root")
        or hacs.get("hide_default_branch") is not True
    ):
        failures.append(
            "HACS ma pobierać standardowy katalog integracji ze stabilnego wydania."
        )
    integrations = sorted(
        p.name
        for p in (ROOT / "custom_components").iterdir()
        if p.is_dir() and p.name != "__pycache__"
    )
    if integrations != ["pge_storage"]:
        failures.append("Repozytorium HACS musi zawierać dokładnie jedną integrację.")
    icon = integration / "brand" / "icon.png"
    if not icon.exists() or not icon.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        failures.append("Brakuje ikony PNG wymaganej przez HACS.")
    if not (integration / "frontend" / "pge-storage-card.js").is_file():
        failures.append("Brakuje karty Lovelace w katalogu instalowanym przez HACS.")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Wydanie v{version}: metadane HACS, wersje i pliki instalacyjne są spójne.")


if __name__ == "__main__":
    main()
