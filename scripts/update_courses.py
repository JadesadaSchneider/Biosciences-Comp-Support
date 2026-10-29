#!/usr/bin/env python3
"""
Fill the "Relevant courses" lists in the training guide from the Biosciences
Computational Biology theme pages.

For every pair of markers in the guide

    <!-- COURSES:<slug>:START -->
    <!-- COURSES:<slug>:END -->

the script fetches
    https://www.ucl.ac.uk/life-sciences/biosciences/computational-biology/<slug>
reads the Modules (Code / Title) table at the bottom of the page, and rewrites
the text between the markers as a bulleted list linked to the UCL module
catalogue. To add a theme, just add a new pair of markers using its URL slug.

If a page can't be fetched or no modules are found, the existing content for
that theme is left untouched and the script exits non-zero at the end so the
failure is visible in GitHub Actions (other themes are still updated).
"""
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDE = REPO_ROOT / "UCL_comp_guides" / "training_and_support_comp_at_UCL.md"

THEME_URL = "https://www.ucl.ac.uk/life-sciences/biosciences/computational-biology/{slug}"
MODULE_URL = "https://www.ucl.ac.uk/module-catalogue/modules/{code}"

CODE_RE = re.compile(r"\b([A-Z]{4}\d{4})\b")
MARKER_RE = re.compile(
    r"(<!-- COURSES:(?P<slug>[a-z0-9-]+):START -->)(?P<body>.*?)(<!-- COURSES:(?P=slug):END -->)",
    re.DOTALL,
)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Biosciences-Comp-Support-bot; +https://github.com/UCL-Biosciences/Biosciences-Comp-Support)"}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_modules(html: str) -> list[tuple[str, str]]:
    """Return [(code, title), ...] from the page's Modules table."""
    soup = BeautifulSoup(html, "html.parser")
    modules: list[tuple[str, str]] = []

    # Preferred: a table whose rows start with a module code
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [clean(c.get_text(" ")) for c in row.find_all(["td", "th"])]
            if len(cells) >= 2 and CODE_RE.fullmatch(cells[0]):
                modules.append((cells[0], cells[1]))

    # Fallback: module lists that aren't real tables ("BIOS0002 Title" per element)
    if not modules:
        for el in soup.find_all(["li", "p", "div"]):
            if el.find(["li", "p", "div"]):  # only leaf-ish elements
                continue
            m = re.match(r"^([A-Z]{4}\d{4})\s*[-–:]?\s*(.+)$", clean(el.get_text(" ")))
            if m:
                modules.append((m.group(1), m.group(2)))

    seen, unique = set(), []
    for code, title in modules:
        if code not in seen:
            seen.add(code)
            unique.append((code, title))
    return unique


def render(modules: list[tuple[str, str]]) -> str:
    return "\n".join(
        f"- [{code}]({MODULE_URL.format(code=code)}) — {title}" for code, title in modules
    )


def main() -> int:
    text = GUIDE.read_text(encoding="utf-8")
    failures = []

    def replace(match: re.Match) -> str:
        slug = match.group("slug")
        url = THEME_URL.format(slug=slug)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            modules = parse_modules(resp.text)
        except requests.RequestException as e:
            print(f"[{slug}] fetch failed: {e}")
            failures.append(slug)
            return match.group(0)
        if not modules:
            print(f"[{slug}] no modules found at {url} - leaving existing content")
            failures.append(slug)
            return match.group(0)
        print(f"[{slug}] {len(modules)} modules")
        return f"{match.group(1)}\n{render(modules)}\n{match.group(4)}"

    new_text = MARKER_RE.sub(replace, text)
    if new_text != text:
        GUIDE.write_text(new_text, encoding="utf-8")
        print("Guide updated.")
    else:
        print("No changes.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
