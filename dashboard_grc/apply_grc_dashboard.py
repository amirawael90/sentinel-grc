"""Adds the GRC pages to a clone of sentinel-task7:
Compliance Center, Policy Library (Z8) and Evidence and Audit, Reports (Z9).

Usage:  python apply_grc_dashboard.py PATH_TO_sentinel-task7
Safe to run again (also after the older apply_z8.py): code files are refreshed, but your data files under
api/app/grc/data and api/app/grc/sample_sources are never overwritten (your feature_status.yaml, policies
and audit log stay as they are). It adds lines to api/app/main.py, api/requirements.txt,
frontend/src/App.tsx and frontend/src/layout/nav.ts.
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEEP_EXISTING = ("api/app/grc/data/", "api/app/grc/sample_sources/")
ROLES = "['Admin', 'Analyst', 'Auditor']"


def read(path: Path):
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    return text, ("\r\n" if "\r\n" in text else "\n")


def write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def find_line(lines, part):
    return next((i for i, line in enumerate(lines) if part in line), None)


def copy_files(target: Path) -> None:
    src_root = HERE / "files"
    for src in sorted(p for p in src_root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        rel = src.relative_to(src_root).as_posix()
        dest = target / rel
        if dest.exists() and rel.startswith(KEEP_EXISTING):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def patch_main(target: Path) -> None:
    path = target / "api" / "app" / "main.py"
    text, nl = read(path)
    if "grc.router" in text:
        print("  main.py: already patched")
        return
    if "search, stats" in text:
        text = text.replace("search, stats", "search, stats, grc", 1)
    lines = text.split(nl)
    i = find_line(lines, "search.router")
    if i is None or "grc" not in text:
        print('  main.py: add by hand:  from app.routers import ..., grc   and   app.include_router(grc.router, prefix="/api")')
        return
    lines.insert(i + 1, 'app.include_router(grc.router, prefix="/api")')
    write(path, nl.join(lines))
    print("  main.py: patched")


def patch_requirements(target: Path) -> None:
    path = target / "api" / "requirements.txt"
    raw = path.read_bytes()
    encoding = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig" if raw[:3] == b"\xef\xbb\xbf" else "utf-8"
    text = raw.decode(encoding)
    if "reportlab" in text.lower():
        print("  requirements.txt: already has reportlab")
        return
    nl = "\r\n" if "\r\n" in text else "\n"
    if not text.endswith(nl):
        text += nl
    text += "reportlab==4.4.10" + nl
    path.write_bytes(text.encode(encoding))
    print("  requirements.txt: added reportlab")


def patch_app(target: Path) -> None:
    path = target / "frontend" / "src" / "App.tsx"
    text, nl = read(path)
    lines = text.split(nl)
    wanted = [("ComplianceCenterPage", "/compliance"), ("PolicyLibraryPage", "/policies"),
              ("EvidenceAuditPage", "/evidence"), ("ReportsPage", "/reports")]
    anchor = 'path="/health"'
    changed = False
    for comp, route in wanted:
        if comp in text:
            j = find_line(lines, f'path="{route}"')
            anchor = f'path="{route}"' if j is not None else anchor
            continue
        i_import = find_line(lines, "export default function App")
        j = find_line(lines, anchor)
        if i_import is None or j is None:
            print(f'  App.tsx: could not patch {comp}. Add by hand: import it and <Route path="{route}" element={{<{comp} />}} />')
            continue
        indent = lines[j][: len(lines[j]) - len(lines[j].lstrip())]
        lines.insert(j + 1, f'{indent}<Route path="{route}" element={{<{comp} />}} />')
        lines.insert(i_import, f"import {{ {comp} }} from './pages/{comp}'")
        text = nl.join(lines)
        anchor = f'path="{route}"'
        changed = True
    if changed:
        write(path, nl.join(lines))
        print("  App.tsx: patched")
    else:
        print("  App.tsx: already patched")


def patch_nav(target: Path) -> None:
    path = target / "frontend" / "src" / "layout" / "nav.ts"
    text, nl = read(path)
    lines = text.split(nl)
    items = [("Compliance Center", "/compliance"), ("Policy Library", "/policies"),
             ("Evidence & Audit", "/evidence"), ("Reports", "/reports")]
    entry = lambda label, route: f"{{ label: '{label}', path: '{route}', roles: {ROLES} }},"  # noqa: E731
    changed = False
    if "title: 'GRC'" not in text:
        i = find_line(lines, "title: 'Platform'")
        if i is None:
            print("  nav.ts: could not find the Platform group. Add a GRC group by hand.")
            return
        block = ["    title: 'GRC',", "    items: ["] + [f"      {entry(*it)}" for it in items] + ["    ],", "  },", "  {"]
        lines[i:i] = block
        changed = True
    else:
        anchor = "title: 'GRC'"
        for label, route in items:
            j = find_line(lines, f"path: '{route}'")
            if j is not None:
                anchor = f"path: '{route}'"
                continue
            k = find_line(lines, anchor)
            if k is None:
                print(f"  nav.ts: could not add {label}. Add it by hand.")
                continue
            indent = lines[k][: len(lines[k]) - len(lines[k].lstrip())] if "path:" in lines[k] else "      "
            lines.insert(k + 1, f"{indent}{entry(label, route)}")
            anchor = f"path: '{route}'"
            changed = True
    if changed:
        write(path, nl.join(lines))
        print("  nav.ts: patched")
    else:
        print("  nav.ts: already patched")


def patch_gitignore(target: Path) -> None:
    path = target / ".gitignore"
    lines_needed = ["# GRC files created when the app runs", "api/app/grc/reports/", "api/app/grc/data/evidence/"]
    if not path.exists():
        print("  .gitignore: not found (skipped)")
        return
    text, nl = read(path)
    if "api/app/grc/reports/" in text:
        print("  .gitignore: already patched")
        return
    if not text.endswith(nl):
        text += nl
    write(path, text + nl + nl.join(lines_needed) + nl)
    print("  .gitignore: patched")


def main(target: Path) -> None:
    if not (target / "api" / "app" / "main.py").exists():
        sys.exit("That folder does not look like sentinel-task7 (api/app/main.py not found).")
    print("Copying files...")
    copy_files(target)
    print("Patching...")
    patch_main(target)
    patch_requirements(target)
    patch_app(target)
    patch_nav(target)
    patch_gitignore(target)
    print("Done. If the API is running, restart it; then run: pip install -r requirements.txt (inside api)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
