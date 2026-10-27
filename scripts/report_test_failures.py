"""Publish only repository test identifiers, never assertion values or logs."""

import os
import re
from pathlib import Path
from xml.etree import ElementTree

source = Path("test-results.xml")
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if source.exists() and summary:
    root = ElementTree.parse(source).getroot()
    identifiers = set()
    for case in root.iter("testcase"):
        if any(result.tag in ("failure", "error") for result in case):
            # Parameter IDs and all failure messages are deliberately excluded.
            module = re.sub(r"[^a-zA-Z0-9_.]", "", case.get("classname", ""))[:128]
            name = re.sub(r"[^a-zA-Z0-9_]", "", case.get("name", "").split("[")[0])[
                :128
            ]
            identifiers.add(f"{module}.{name}")
    with Path(summary).open("a") as output:
        output.write("## Failed test identifiers (no logs or values)\n\n")
        output.write("\n".join(f"- `{name}`" for name in sorted(identifiers)))
