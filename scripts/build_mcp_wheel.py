"""Derive an MCP-only wheel from a fully built doc-mcp wheel."""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import zipfile
from pathlib import Path


_MCP_REQUIREMENTS = (
    "Requires-Dist: mcp==1.28.1",
    "Requires-Dist: PyYAML==6.0.3",
    "Requires-Dist: python-dotenv==1.2.2",
)
_MCP_ENTRY_POINTS = "[console_scripts]\ndocmcp-server = docmcp.main:main\n"
_MCP_DISTRIBUTION_NAME = "doc-mcp-no-crawler"
_MCP_WHEEL_NAME = "doc_mcp_no_crawler"


def _hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).decode().rstrip("=")


def build_mcp_wheel(source: Path, output_dir: Path) -> Path:
    with zipfile.ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}

    metadata_names = [name for name in files if name.endswith(".dist-info/METADATA")]
    if len(metadata_names) != 1:
        raise ValueError(f"Expected exactly one wheel METADATA file, found {metadata_names}")
    metadata_name = metadata_names[0]
    dist_info = metadata_name.removesuffix("/METADATA")
    metadata = files[metadata_name].decode("utf-8")
    version_match = re.search(r"^Version: (?P<version>[^\n]+)$", metadata, re.MULTILINE)
    if version_match is None:
        raise ValueError(f"Wheel metadata has no Version field: {source}")
    version = version_match.group("version")
    mcp_version = version
    metadata = re.sub(r"^Requires-Dist: .*\n", "", metadata, flags=re.MULTILINE)
    metadata = metadata.replace("Name: doc-mcp\n", f"Name: {_MCP_DISTRIBUTION_NAME}\n", 1)
    metadata = metadata.replace(f"Version: {version}", f"Version: {mcp_version}", 1)
    metadata = metadata.replace(
        "Requires-Python: >=3.11\n",
        "Requires-Python: >=3.11\n" + "\n".join(_MCP_REQUIREMENTS) + "\n",
        1,
    )

    mcp_dist_info = f"{_MCP_WHEEL_NAME}-{mcp_version}.dist-info"
    renamed: dict[str, bytes] = {}
    for name, data in files.items():
        new_name = name.replace(dist_info, mcp_dist_info, 1)
        if name == metadata_name:
            data = metadata.encode("utf-8")
        if name.endswith(".dist-info/entry_points.txt"):
            data = _MCP_ENTRY_POINTS.encode("utf-8")
        if not new_name.endswith(".dist-info/RECORD"):
            renamed[new_name] = data

    record_name = next(name for name in renamed if name.endswith(".dist-info/WHEEL")).replace(
        "/WHEEL", "/RECORD"
    )
    record_lines = [f"{name},{_hash(data)},{len(data)}" for name, data in sorted(renamed.items())]
    record_lines.append(f"{record_name},,")
    renamed[record_name] = ("\n".join(record_lines) + "\n").encode("utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / source.name.replace(
        f"doc_mcp-{version}-", f"{_MCP_WHEEL_NAME}-{mcp_version}-", 1
    )
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(renamed.items()):
            archive.writestr(name, data)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(build_mcp_wheel(args.wheel, args.output_dir))


if __name__ == "__main__":
    main()
