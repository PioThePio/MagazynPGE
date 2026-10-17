"""Package only installable integration files and user documentation."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads(
        (ROOT / "custom_components/pge_storage/manifest.json").read_text()
    )
    output = ROOT / "dist" / f"MagazynPGE-{manifest['version']}.zip"
    output.parent.mkdir(exist_ok=True)
    files = [ROOT / "README.md"]
    for directory in ("custom_components/pge_storage", "dashboards", "docs"):
        files.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix in {".py", ".json", ".js", ".yaml", ".md", ".png"}
        )
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(ROOT))
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert "custom_components/pge_storage/manifest.json" in archive.namelist()
    print(output)


if __name__ == "__main__":
    main()
