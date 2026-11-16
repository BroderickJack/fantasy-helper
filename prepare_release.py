"""Update the static site's version and create its portable upload archive."""

import argparse
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help="Release version, e.g. 1.0.1; defaults to website/package.json")
    args = parser.parse_args()
    package_path = ROOT / "website/package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    version = (args.version or package["version"]).removeprefix("v")
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        parser.error("Use a release version such as 1.0.0 or v1.0.0.")

    dist = ROOT / "website/dist"
    pages = {}
    badge = f'<span class="site-version" aria-label="Site version">v{version}</span>'
    for path in sorted(dist.glob("*.html")):
        html = path.read_text(encoding="utf-8")
        if html.count("</footer>") != 1:
            parser.error(f"Expected one page footer in {path.name}.")
        if 'class="site-version"' in html:
            html, count = re.subn(r'<span class="site-version"[^>]*>[^<]*</span>', lambda _: badge, html)
            if count != 1:
                parser.error(f"Expected one version badge in {path.name}.")
        else:
            html = html.replace("</footer>", f"{badge}</footer>")
        pages[path] = html
    if not pages:
        parser.error("No website pages found.")

    package["version"] = version
    package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    for path, html in pages.items():
        if path.read_text(encoding="utf-8") != html:
            path.write_text(html, encoding="utf-8")
    archive = ROOT / "website/qrffl-site.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        for path in sorted(dist.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(dist).as_posix())
    print(f"Prepared v{version}: {len(pages)} page footers and {archive.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
