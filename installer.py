#!/usr/bin/env python3
"""Install published OKE RM configurations as private Resource Manager templates."""

import argparse
import base64
import configparser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

SOURCE = "oracle-devrel/technology-engineering"
INSTALLER = "oke-rm-private-templates"
KINDS = {"networking": ("infra.zip", "oke-rm-networking"),
         "cluster": ("oke.zip", "oke-rm-cluster")}


def request_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": INSTALLER,
                                                  "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def latest_release():
    # This repository releases several assets; /releases/latest is not OKE-specific.
    for page in range(1, 21):
        releases = request_json(f"https://api.github.com/repos/{SOURCE}/releases?per_page=100&page={page}")
        for release in releases:
            if (re.fullmatch(r"oke-rm-\d+\.\d+\.\d+", release["tag_name"])
                    and not release["draft"] and not release["prerelease"]):
                return release
        if len(releases) < 100:
            break
    raise ValueError("No published stable OKE RM release found.")


def defaults():
    config = configparser.ConfigParser(interpolation=None)
    config.read(Path(os.environ.get("OCI_CLI_CONFIG_FILE", "~/.oci/config")).expanduser())
    profile = os.environ.get("OCI_CLI_PROFILE", "DEFAULT")
    settings = config[profile] if profile in config else {}
    tenancy = os.environ.get("OCI_TENANCY", os.environ.get("OCI_CLI_TENANCY", settings.get("tenancy", "")))
    region = os.environ.get("OCI_REGION", os.environ.get("OCI_CLI_REGION", settings.get("region", "")))
    return tenancy, region


def prompt(label, default=""):
    value = input(f"{label}" + (f" [{default}]" if default else "") + ": ").strip()
    return value or default


def oci(*args):
    result = subprocess.run(["oci", *args, "--output", "json"],
                            text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "OCI CLI command failed.")
    return json.loads(result.stdout)


def template_items(response):
    data = response.get("data")
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("display-name"), str)
            for item in items):
        raise ValueError("Unexpected OCI template list response: expected data.items containing template objects.")
    return items


def existing_template(templates, name, kind, version):
    matches = [t for t in templates if t["display-name"] == name
               and t.get("lifecycle-state") not in ("DELETED", "DELETING")]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"Several templates named {name!r} exist. Choose another name.")
    template = matches[0]
    tags = template.get("freeform-tags") or {}
    expected = {"installer": INSTALLER, "asset": "oke-rm", "template_type": kind,
                "release_version": version}
    if template.get("lifecycle-state") == "ACTIVE" and all(tags.get(k) == v for k, v in expected.items()):
        return template
    raise ValueError(f"Template {name!r} already exists with different content/version or ownership. "
                     "Choose another name; this installer will not overwrite it.")


def archive_url(release, filename):
    assets = [a for a in release.get("assets", []) if a["name"] == filename]
    if len(assets) != 1:
        raise ValueError(f"Release is missing the required asset {filename}.")
    url = assets[0]["browser_download_url"]
    expected = f"https://github.com/{SOURCE}/releases/download/{release['tag_name']}/"
    if not url.startswith(expected):
        raise ValueError("Unexpected release asset URL.")
    return url


def create_template(archive, compartment, region, name, kind, version, release_url):
    # Unlike stack upload commands, template creation expects base64 ZIP contents.
    # Pass a JSON file to avoid command-line length limits for larger archives.
    payload = {
        "compartmentId": compartment,
        "configSource": base64.b64encode(archive.read_bytes()).decode("ascii"),
        "displayName": name,
        "description": f"OKE RM {kind} template, release {version}.",
        "longDescription": f"Installed from {release_url}. Creates no infrastructure until a stack is applied.",
        "freeformTags": {"installer": INSTALLER, "asset": "oke-rm", "template_type": kind,
                        "release_version": version},
    }
    request_file = archive.with_suffix(".request.json")
    request_file.write_text(json.dumps(payload), encoding="utf-8")
    return oci("resource-manager", "template", "create", "--region", region,
               "--from-json", f"file://{request_file}", "--wait-for-state", "ACTIVE")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate and download archives without creating templates")
    args = parser.parse_args()
    if not shutil.which("oci"):
        raise ValueError("OCI CLI is required. Run this installer in OCI Cloud Shell.")
    tenancy, default_region = defaults()
    region = prompt("Target region", default_region)
    compartment = prompt("Template compartment OCID (tenancy OCID = root)", tenancy)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+-\d+", region):
        raise ValueError("A valid target region is required.")
    if not re.fullmatch(r"ocid1\.(?:compartment|tenancy)\.[A-Za-z0-9._-]+", compartment):
        raise ValueError("A compartment or tenancy OCID is required.")
    selection = prompt("Templates: both, networking, or cluster", "both")
    if selection not in ("both", *KINDS):
        raise ValueError("Select both, networking, or cluster.")
    latest = latest_release()
    version = prompt("OKE RM release version", latest["tag_name"].removeprefix("oke-rm-"))
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Use a release version such as 1.4.0, not a Kubernetes version.")
    tag = f"oke-rm-{version}"
    release = latest if tag == latest["tag_name"] else request_json(f"https://api.github.com/repos/{SOURCE}/releases/tags/{tag}")
    if release["draft"] or release["prerelease"]:
        raise ValueError("Only published stable releases are supported.")
    kinds = list(KINDS) if selection == "both" else [selection]
    names = {k: prompt(f"{k.title()} template name", KINDS[k][1]) for k in kinds}
    if any(not n for n in names.values()) or len(set(names.values())) != len(names):
        raise ValueError("Template names must be nonempty and distinct.")
    templates = template_items(oci("resource-manager", "template", "list", "--compartment-id", compartment,
                                   "--template-category-id", "3", "--all", "--region", region))
    existing = {k: existing_template(templates, names[k], k, version) for k in kinds}
    urls = {k: archive_url(release, KINDS[k][0]) for k in kinds}
    print(f"\nRegion: {region}\nCompartment: {compartment}\nRelease: {tag}")
    for kind in kinds:
        print(f"  {names[kind]}: {'skip (already installed)' if existing[kind] else 'create'}")
    if not args.dry_run and prompt("Create the listed private templates? yes/no", "no").lower() != "yes":
        print("Cancelled. No templates were created.")
        return
    # Validate every download before creating anything, avoiding partial installs on bad assets.
    with tempfile.TemporaryDirectory(prefix="oke-rm-templates-") as directory:
        archives = {}
        for kind in kinds:
            if existing[kind]:
                continue
            target = Path(directory) / KINDS[kind][0]
            request = urllib.request.Request(urls[kind], headers={"User-Agent": INSTALLER})
            with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
                shutil.copyfileobj(response, output)
            with zipfile.ZipFile(target) as archive:
                if archive.testzip() or "schema.yaml" not in archive.namelist():
                    raise ValueError(f"Invalid Resource Manager archive: {target.name}")
            archives[kind] = target
        if args.dry_run:
            print("Dry run passed. No templates were created.")
            return
        for kind in kinds:
            if existing[kind]:
                print(f"Skipped {names[kind]}: {existing[kind]['id']}")
                continue
            result = create_template(archives[kind], compartment, region, names[kind],
                                     kind, version, release["html_url"])
            print(f"Created {names[kind]}: {result['data']['id']}")
    print("Done. In Resource Manager, choose Create stack > Private template.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, zipfile.BadZipFile, EOFError, KeyboardInterrupt) as error:
        raise SystemExit(f"Installer stopped: {error}")
