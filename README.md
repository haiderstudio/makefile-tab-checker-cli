# makefile-tab-checker-cli

Check Makefile recipe lines use tabs, not spaces — fail CI when one does not.

[![CI](https://github.com/haiderstudio/makefile-tab-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/makefile-tab-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`makefile_tab_checker` reads each Makefile,
finds every recipe line indented with spaces
instead of a tab, and reports each one with the
file and the line number. It also reports a
tab-indented line that is not part of any recipe.
It exits 1 when any recipe line is wrong, so it
can fail a CI run. A file whose recipe lines all
start with a tab exits 0.

- A space where make expects a tab is the classic
  "missing separator" build failure — the build
  breaks, the error points at the wrong line, and
  the cause is invisible in most editors. This
  names the exact line, and the fix is one
  keystroke per line.
- A tab-indented line with no recipe above it is
  reported too, with its own wording — make
  rejects it as "recipe commences before first
  target".
- A recipe stays open until a line that is not
  indented, blank, or a comment: a variable
  assignment, another target, or a directive ends
  it. Blank lines and comment lines do not end a
  recipe. Lines inside a `define ... endef` block
  are variable text, not recipes, and are skipped.
  A line ending in a backslash continues onto the
  next line, so the next line is part of the same
  line and is never checked on its own.
- A file given directly on the command line is
  always checked, whatever its name. A folder is
  walked for files named `Makefile`, `makefile`,
  or `GNUmakefile`, or ending in `.mk` or `.mak`,
  recursively by default (`--no-recursive` stops
  at the top level). `.git` folders are never
  walked, and directory links are never followed.
- `--json` prints the result as JSON, and
  `--stdin` checks one Makefile read from
  standard input.

## Who it is for

Every project with a Makefile — a C build, a
documentation build, a task runner. One space
where a tab belongs and the whole build stops
with an error that points at the wrong line, and
the cause is invisible in most editors. This is
the gate that stops it at the pull request.

## What it does NOT do

- It does not check that the Makefile is correct
  or that the build works. A recipe that runs the
  wrong command is a different job — this tool
  only checks the indent.
- It does not check trailing whitespace or mixed
  indent in general files. That is repo #42,
  whitespace-checker-cli — it checks trailing
  whitespace, tabs and mixed indent in general
  files, but it does not know a Makefile recipe
  line must be a tab, and it does not know a
  space-indented recipe line is a build break.
- It does not check variable assignments, target
  names, or whether a target's prerequisites
  exist.
- It never rewrites a file, and it never touches
  the network.

## How this differs

- A fresh search of GitHub on Nov 15, 2026 found
  0 results for `"makefile-tab-checker-cli"` and 0
  results for `makefile tab checker` — a
  completely empty field.
- No rival checks Makefile recipe indents.

## Install

```sh
git clone https://github.com/haiderstudio/makefile-tab-checker-cli.git
cd makefile-tab-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one Makefile:

```sh
python3 src/makefile_tab_checker.py Makefile
```

A file whose recipe lines all start with a tab passes:

```sh
$ python3 src/makefile_tab_checker.py examples/clean.mk
OK — 1 file(s) checked, every recipe line starts with a tab.
```

A file with space-indented recipe lines fails, with the
file and line for each one:

```sh
$ python3 src/makefile_tab_checker.py examples/flagged.mk
FAIL examples/flagged.mk: line 6 recipe line indented with spaces, not a tab — make will report 'missing separator'
FAIL examples/flagged.mk: line 12 recipe line indented with spaces, not a tab — make will report 'missing separator'
Checked 1 file(s), 2 recipe line(s) with the wrong indent in 1 file(s).
```

Check a whole folder (`Makefile` / `.mk` / `.mak` files only):

```sh
$ python3 src/makefile_tab_checker.py examples/
FAIL examples/flagged.mk: line 6 recipe line indented with spaces, not a tab — make will report 'missing separator'
FAIL examples/flagged.mk: line 12 recipe line indented with spaces, not a tab — make will report 'missing separator'
Checked 3 file(s), 2 recipe line(s) with the wrong indent in 1 file(s).
```

Check one Makefile from standard input:

```sh
$ printf 'all: app\n    true\n' | python3 src/makefile_tab_checker.py --stdin
FAIL <stdin>: line 2 recipe line indented with spaces, not a tab — make will report 'missing separator'
Checked 1 file(s), 1 recipe line(s) with the wrong indent in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/makefile_tab_checker.py --json examples/flagged.mk
{
  "files": [
    {
      "path": "examples/flagged.mk",
      "findings": [
        {
          "line": 6,
          "reason": "recipe line indented with spaces, not a tab — make will report 'missing separator'"
        },
        {
          "line": 12,
          "reason": "recipe line indented with spaces, not a tab — make will report 'missing separator'"
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 2
}
```

Exit codes: 0 when every recipe line starts with a
tab, 1 when any recipe line is wrong or a file
cannot be read, 2 for a usage error (a missing path,
a bad flag, or no Makefile found).

## Examples

A comment between a target and its recipe does not
end the recipe, and a backslash-continued variable
line is one logical line — `examples/edge.mk` has
both, plus a `define` block, and it passes:

```sh
$ python3 src/makefile_tab_checker.py examples/edge.mk
OK — 1 file(s) checked, every recipe line starts with a tab.
```

A tab followed by spaces is still a tab-indented
recipe line, so it passes — `examples/flagged.mk`
holds one under its `install:` target, and only
the two space-indented lines fail:

```sh
$ python3 src/makefile_tab_checker.py examples/flagged.mk
FAIL examples/flagged.mk: line 6 recipe line indented with spaces, not a tab — make will report 'missing separator'
FAIL examples/flagged.mk: line 12 recipe line indented with spaces, not a tab — make will report 'missing separator'
Checked 1 file(s), 2 recipe line(s) with the wrong indent in 1 file(s).
```

A tab-indented line before any target is not part
of a recipe, so it fails:

```sh
$ printf '\techo stray\n' | python3 src/makefile_tab_checker.py --stdin
FAIL <stdin>: line 1 tab-indented line is not part of any recipe — make will report 'recipe commences before first target'
Checked 1 file(s), 1 recipe line(s) with the wrong indent in 1 file(s).
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_makefile_tab_checker.py
```

The tests cover recipe detection (a tab recipe
passes, a space recipe fails, a two-space recipe
fails, a line starting with a space then a tab
fails, a tab then a space passes, several bad
recipes in document order, a stray tab before the
first target fails, a stray tab after a variable
fails, a space-indented line where no recipe is
open passes, blank lines do not end a recipe,
comment lines do not end a recipe, a variable
assignment ends a recipe, a second target opens a
new recipe, a pattern rule opens a recipe, a
`.PHONY` target opens a recipe, a double-colon
rule opens a recipe, a target-specific variable
is a target, `:=`, `?=`, and `+=` assignments are
not targets, an empty file passes, a file with
only variables passes, a file with only comments
passes, a semicolon recipe on the target line
passes, backslash-continued variable, recipe, and
target lines are not checked on their own, a
`define` block is skipped, a tab-indented comment
inside a recipe passes), the CLI (exit 0/1/2,
folder walking for `Makefile`, `makefile`,
`GNUmakefile`, and `.mak` files, nested folders,
`--no-recursive`, `--exclude`, `.git` skipped, a
direct file checked whatever its name, duplicate
paths checked once, `--json` output, `--stdin`,
bad flags, missing paths, empty folders,
`--version`, a non-UTF-8 file reported, input
files left unchanged, the tool run from another
folder and under a changed HOME), the bundled
examples (sample output compared byte-for-byte
against a fresh run, and the README-quoted outputs
checked against it), and hygiene checks (no
placeholder text, no absolute paths, no real
secrets outside the tests and examples, stdlib
imports only, no network use in the source,
`.env` first in `.gitignore`, CI file runs the
test file, README names the neighbouring repo).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of checking Makefile indents is not new — the
"missing separator" error is one of make's oldest
traps — but no existing tool does this one job,
checking that every recipe line in local Makefiles
starts with a tab, as a tested command-line gate
with a CI exit code, as the search above shows —
and every line of code here is original, built on
nothing but Python's standard library.
