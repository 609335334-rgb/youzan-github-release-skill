#!/usr/bin/env python3
"""Build and finalize independent releases for the Youzan AIGC video plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REPOSITORY = "609335334-rgb/youzan-aigc-plugin-updates"
PLUGIN_ID = "video_plugin_youzan_aigc"
VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,3}$")
MAIN_VERSION_RE = re.compile(r'(_PLUGIN_VERSION\s*=\s*")[^"]+(" )?')


def fail(message: str) -> None:
    raise SystemExit(f"Error: {message}")


def version_key(value: str) -> tuple[int, ...]:
    if not VERSION_RE.fullmatch(value):
        fail(f"invalid version: {value}")
    return tuple(int(part) for part in value.split("."))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_current_version(plugin_dir: Path) -> str:
    main_path = plugin_dir / "main.py"
    info_path = plugin_dir / "info.json"
    match = re.search(r'_PLUGIN_VERSION\s*=\s*"([^"]+)"', main_path.read_text(encoding="utf-8"))
    if not match:
        fail("main.py does not contain _PLUGIN_VERSION")
    main_version = match.group(1)
    info_version = str(json.loads(info_path.read_text(encoding="utf-8")).get("version", ""))
    if main_version != info_version:
        fail(f"version mismatch: main.py={main_version}, info.json={info_version}")
    version_key(main_version)
    return main_version


def run_checks(plugin_dir: Path) -> None:
    python = sys.executable
    with tempfile.TemporaryDirectory(prefix="youzan_release_compile_") as temp_dir:
        try:
            py_compile.compile(
                str(plugin_dir / "main.py"),
                cfile=str(Path(temp_dir) / "main.pyc"),
                doraise=True,
            )
        except py_compile.PyCompileError as exc:
            fail(f"syntax validation failed: {exc.msg}")
    completed = subprocess.run([python, "-B", "test_plugin.py"], cwd=plugin_dir, text=True)
    if completed.returncode:
        fail("plugin tests failed")


def replace_version(text: str, version: str) -> str:
    updated, count = re.subn(r'(_PLUGIN_VERSION\s*=\s*")[^"]+(" )?', lambda m: f'{m.group(1)}{version}{m.group(2) or ""}', text, count=1)
    if count != 1:
        fail("could not update _PLUGIN_VERSION in staged main.py")
    return updated


def update_test_version(text: str, old: str, new: str) -> str:
    return text.replace(old, new)


def stage_name(version: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"youzan-plugin-{version}-{timestamp}"


def prepare(args: argparse.Namespace) -> None:
    plugin_dir = Path(args.plugin_dir).resolve()
    if not plugin_dir.is_dir():
        fail(f"plugin directory not found: {plugin_dir}")
    if not args.changelog.strip():
        fail("changelog cannot be empty")
    current = load_current_version(plugin_dir)
    if version_key(args.version) <= version_key(current):
        fail(f"new version must be greater than {current}")
    run_checks(plugin_dir)

    stage_dir = Path(tempfile.gettempdir()) / "youzan-github-release" / stage_name(args.version)
    payload_dir = stage_dir / "payload"
    stage_dir.mkdir(parents=True, exist_ok=False)
    ignored = shutil.ignore_patterns("__pycache__", "*.pyc", "releases", ".release-tools", "release_plugin.py", "一键发布新版本.bat")
    shutil.copytree(plugin_dir, payload_dir, ignore=ignored)

    main_path = payload_dir / "main.py"
    main_path.write_text(replace_version(main_path.read_text(encoding="utf-8"), args.version), encoding="utf-8")
    info_path = payload_dir / "info.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    info["version"] = args.version
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    test_path = payload_dir / "test_plugin.py"
    if test_path.exists():
        test_path.write_text(update_test_version(test_path.read_text(encoding="utf-8"), current, args.version), encoding="utf-8")

    zip_name = f"youzan-aigc-plugin-v{args.version}.zip"
    zip_path = stage_dir / zip_name
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        for path in payload_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(payload_dir))
    checksum = sha256(zip_path)
    manifest = {
        "plugins": [{
            "id": PLUGIN_ID,
            "version": args.version,
            "changelog": args.changelog,
            "download_url": f"https://raw.githubusercontent.com/{REPOSITORY}/main/releases/{zip_name}",
            "sha256": checksum,
            "published_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }]
    }
    manifest_path = stage_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "repository": REPOSITORY,
        "current_version": current,
        "version": args.version,
        "changelog": args.changelog,
        "zip": str(zip_path),
        "sha256": checksum,
        "manifest": str(manifest_path),
        "upload_order": [
            f"releases/{zip_name}",
            "main.py",
            "info.json",
            "README.md",
            "manifest.json",
        ],
    }
    (stage_dir / "release-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def finalize(args: argparse.Namespace) -> None:
    plugin_dir = Path(args.plugin_dir).resolve()
    stage_dir = Path(args.stage_dir).resolve()
    summary_path = stage_dir / "release-summary.json"
    payload_dir = stage_dir / "payload"
    if not summary_path.is_file() or not payload_dir.is_dir():
        fail("invalid staged release directory")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    current = load_current_version(plugin_dir)
    if current != summary["current_version"]:
        fail(f"local version changed since prepare: expected {summary['current_version']}, found {current}")
    for name in ("main.py", "info.json", "test_plugin.py"):
        source = payload_dir / name
        if source.exists():
            shutil.copy2(source, plugin_dir / name)
    print(f"Local plugin finalized at {summary['version']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(required=True)
    prepare_parser = subcommands.add_parser("prepare")
    prepare_parser.add_argument("--plugin-dir", required=True)
    prepare_parser.add_argument("--version", required=True)
    prepare_parser.add_argument("--changelog", required=True)
    prepare_parser.set_defaults(handler=prepare)
    finalize_parser = subcommands.add_parser("finalize")
    finalize_parser.add_argument("--plugin-dir", required=True)
    finalize_parser.add_argument("--stage-dir", required=True)
    finalize_parser.set_defaults(handler=finalize)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
