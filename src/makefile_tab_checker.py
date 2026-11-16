#!/usr/bin/env python3
"""Check Makefile recipe lines use tabs, not spaces.

Run: python3 src/makefile_tab_checker.py Makefile
     python3 src/makefile_tab_checker.py project/
     python3 src/makefile_tab_checker.py --stdin < Makefile

A space where make expects a tab is the classic
"missing separator" build failure — the build
breaks, the error points at the wrong line, and
the cause is invisible in most editors. This tool
reads each Makefile you point it at, finds every
recipe line indented with spaces instead of a
tab, and reports each one with the file and the
line number. It also reports a tab-indented line
that is not part of any recipe — make rejects
that too. It exits 1 when any recipe line is
wrong, so it can fail a CI run. A file whose
recipe lines all start with a tab exits 0.

A recipe line is a line indented with a tab that
follows a target line (a line like "build: main.o"
at column zero). The recipe stays open until a
line that is not indented, blank, or a comment:
a variable assignment, another target, or a
directive ends it. A variable assignment or a
target line is never a recipe, however it is
indented, and a space-indented line where no
recipe is open is left alone — make strips
leading whitespace there, so it is not a bug.

Lines inside a "define ... endef" block are
variable text, not recipes, and are skipped.
A line ending in a backslash continues onto the
next line, so the next line is part of the same
line and is never checked on its own. Blank
lines and comment lines do not end a recipe.

It never rewrites a file, never touches the
network, and reads only the files and folders
you point it at.
"""

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

__version__ = "1.0.0"

MAKEFILE_NAMES = ("makefile", "gnumakefile")
MAKEFILE_SUFFIXES = (".mk", ".mak")


def _is_target_line(text):
    """True when a column-zero line opens a rule.

    A target line has a colon before any equals
    sign: "build: main.o", "clean:", "%.o: %.c",
    ".PHONY: clean", "target: VAR = x". A line
    with an equals sign before any colon is a
    variable assignment, not a target.
    """
    colon = text.find(":")
    if colon < 0:
        return False
    if colon + 1 < len(text) and text[colon + 1] == "=":
        return False
    if colon > 0 and text[colon - 1] in "?!+":
        return False
    equals = text.find("=")
    if equals >= 0 and equals < colon:
        return False
    return True


def check_text(text):
    """Check one Makefile's text.

    Returns a list of findings, each {"line": int,
    "reason": str}, in document order.
    """
    findings = []
    recipe_open = False
    in_define = False
    continued = False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r")
        if continued:
            continued = line.rstrip().endswith("\\")
            continue
        if line.rstrip().endswith("\\"):
            # A continued line is one logical line;
            # the next physical line is not checked.
            continued = True
        stripped = line.lstrip(" \t")
        if stripped == "":
            continue
        if in_define:
            if stripped.startswith("endef"):
                in_define = False
                recipe_open = False
            continue
        if stripped.startswith("#"):
            continue
        if line[0] in " \t":
            if line[0] == " ":
                if recipe_open:
                    findings.append({
                        "line": number,
                        "reason": ("recipe line indented with spaces, "
                                   "not a tab — make will report "
                                   "'missing separator'"),
                    })
            else:
                if not recipe_open:
                    findings.append({
                        "line": number,
                        "reason": ("tab-indented line is not part of "
                                   "any recipe — make will report "
                                   "'recipe commences before first "
                                   "target'"),
                    })
            continue
        # A column-zero line: it ends any open recipe.
        recipe_open = False
        first = stripped.split(None, 1)[0] if stripped.split() else ""
        if first in ("define",):
            in_define = True
            continue
        if _is_target_line(stripped):
            recipe_open = True
    return findings


def check_file(path):
    """Check one file. Returns (findings, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    return check_text(text), None


def _is_makefile(path):
    name = Path(path).name
    if name.lower() in MAKEFILE_NAMES:
        return True
    return name.lower().endswith(MAKEFILE_SUFFIXES)


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of Makefiles.

    A file given directly is always checked, whatever
    its name. A folder is walked for files named
    Makefile, makefile, or GNUmakefile, or ending in
    .mk or .mak, recursively by default.
    .git folders are never walked, and directory links
    are never followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(dirpath) / name
                    if not _is_makefile(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_finding(path, finding):
    """One human-readable line for one bad recipe line."""
    return ("FAIL %s: line %d %s"
            % (path, finding["line"], finding["reason"]))


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no Makefile found", file=sys.stderr)
        return 2
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, error = check_file(path)
        count = len(bad) + (1 if error else 0)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2, ensure_ascii=False))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d recipe line(s) with the "
                  "wrong indent in %d file(s)."
                  % (len(files), findings, files_with_findings))
        else:
            print("OK — %d file(s) checked, every recipe line "
                  "starts with a tab." % len(files))
    return 1 if findings else 0


def run_stdin(as_json=False):
    """Check one Makefile read from standard input."""
    text = sys.stdin.read()
    bad = check_text(text)
    findings = len(bad)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "error": None}],
             "checked": 1, "findings": findings},
            indent=2, ensure_ascii=False))
    else:
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d recipe line(s) with the "
                  "wrong indent in 1 file(s)." % findings)
        else:
            print("OK — 1 file(s) checked, every recipe line "
                  "starts with a tab.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="makefile_tab_checker",
        description="Check Makefile recipe lines use tabs, "
                    "not spaces, fail CI when one does not. "
                    "Report-only: it never edits a file.")
    parser.add_argument("paths", nargs="*",
                        help="Makefiles or folders to walk")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one Makefile from standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one Makefile or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
