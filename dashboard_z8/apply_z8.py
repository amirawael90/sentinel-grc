"""Adds the Compliance Center and Policy Library pages (Z8) to a clone of sentinel-task7.

Usage:  python apply_z8.py PATH_TO_sentinel-task7
Safe to run twice. It copies the new files and adds a few lines to
api/app/main.py, frontend/src/App.tsx and frontend/src/layout/nav.ts.
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(path: Path):
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    return text, ("\r\n" if "\r\n" in text else "\n")


def write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def insert_after(text, anchor_line_part, new_lines, nl):
    """Insert new_lines after the first line that contains anchor_line_part."""
    lines = text.split(nl)
    for i, line in enumerate(lines):
        if anchor_line_part in line:
            return nl.join(lines[: i + 1] + new_lines + lines[i + 1:])
    return None


def insert_before(text, anchor_line_part, new_lines, nl):
    lines = text.split(nl)
    for i, line in enumerate(lines):
        if anchor_line_part in line:
            return nl.join(lines[:i] + new_lines + lines[i:])
    return None


def patch(path: Path, marker: str, edits, manual_hint: str) -> None:
    text, nl = read(path)
    if marker in text:
        print(f"  {path.name}: already patched")
        return
    for kind, anchor, lines in edits:
        fn = insert_after if kind == "after" else insert_before
        result = fn(text, anchor, lines, nl)
        if result is None:
            print(f"  {path.name}: could not find '{anchor}'. Add this by hand:\n{manual_hint}")
            return
        text = result
    write(path, text)
    print(f"  {path.name}: patched")


def main(target: Path) -> None:
    if not (target / "api" / "app" / "main.py").exists():
        sys.exit("That folder does not look like sentinel-task7 (api/app/main.py not found).")
    print("Copying files...")
    shutil.copytree(HERE / "files", target, dirs_exist_ok=True)

    print("Patching...")
    main_py = target / "api" / "app" / "main.py"
    text, nl = read(main_py)
    if "grc" not in text:
        text = text.replace("search, stats", "search, stats, grc", 1) if "search, stats" in text else text
        write(main_py, text)
    patch(main_py, "grc.router", [("after", "search.router", ['app.include_router(grc.router, prefix="/api")'])],
          '  from app.routers import ..., grc   and   app.include_router(grc.router, prefix="/api")')

    patch(target / "frontend" / "src" / "App.tsx", "ComplianceCenterPage",
          [("before", "export default function App", ["import { ComplianceCenterPage } from './pages/ComplianceCenterPage'",
                                                      "import { PolicyLibraryPage } from './pages/PolicyLibraryPage'", ""]),
           ("after", 'path="/health"', ['                <Route path="/compliance" element={<ComplianceCenterPage />} />',
                                        '                <Route path="/policies" element={<PolicyLibraryPage />} />'])],
          '  import both pages and add <Route path="/compliance" .../> and <Route path="/policies" .../> next to /health')

    patch(target / "frontend" / "src" / "layout" / "nav.ts", "/compliance",
          [("before", "title: 'Platform'", [
              "    title: 'GRC',",
              "    items: [",
              "      { label: 'Compliance Center', path: '/compliance', roles: ['Admin', 'Analyst', 'Auditor'] },",
              "      { label: 'Policy Library', path: '/policies', roles: ['Admin', 'Analyst', 'Auditor'] },",
              "    ],",
              "  },",
              "  {"])],
          "  add a group with title 'GRC' and the items /compliance and /policies")
    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
