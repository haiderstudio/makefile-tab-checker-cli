#!/usr/bin/env python3
"""Tests for makefile_tab_checker — stdlib unittest only.

Every Makefile in this file is made up for testing.
No real secret appears anywhere in this file.
"""

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import makefile_tab_checker as checker

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src/makefile_tab_checker.py"


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text):
    return checker.check_text(text)


class TestRecipeDetection(unittest.TestCase):
    def test_tab_recipe_passes(self):
        self.assertEqual(
            findings_of("all: app\n\tgcc -o app app.o\n"), [])

    def test_space_recipe_fails(self):
        bad = findings_of("all: app\n    gcc -o app app.o\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)
        self.assertIn("spaces", bad[0]["reason"])
        self.assertIn("missing separator", bad[0]["reason"])

    def test_two_space_recipe_fails(self):
        bad = findings_of("clean:\n  rm -f app\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)

    def test_mixed_indent_starts_with_space_fails(self):
        bad = findings_of("all: app\n \tgcc -o app app.o\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)

    def test_tab_then_space_recipe_passes(self):
        self.assertEqual(
            findings_of("install: app\n\t cp app /usr/local/bin/app\n"),
            [])

    def test_multiple_bad_recipes_in_document_order(self):
        text = ("all: app\n"
                "    gcc -o app app.o\n"
                "main.o: main.c\n"
                "\tgcc -c main.c\n"
                "clean:\n"
                "  rm -f app\n")
        bad = findings_of(text)
        self.assertEqual([f["line"] for f in bad], [2, 6])

    def test_stray_tab_before_first_target_fails(self):
        bad = findings_of("\techo stray\nall: app\n\ttrue\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertIn("not part of any recipe", bad[0]["reason"])

    def test_stray_tab_after_variable_fails(self):
        bad = findings_of("CC = gcc\n\techo stray\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)

    def test_space_indent_with_no_recipe_open_passes(self):
        # A space-indented variable line is not a recipe.
        self.assertEqual(
            findings_of("FLAGS = -Wall\n    -O2\n"), [])

    def test_blank_lines_do_not_end_recipe(self):
        text = ("all: app\n"
                "\tgcc -o app app.o\n"
                "\n"
                "    gcc -c main.c\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 4)

    def test_comment_lines_do_not_end_recipe(self):
        text = ("all: app\n"
                "# a comment\n"
                "    gcc -o app app.o\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 3)

    def test_variable_assignment_ends_recipe(self):
        text = ("all: app\n"
                "\tgcc -o app app.o\n"
                "CC = gcc\n"
                "    not a recipe\n")
        self.assertEqual(findings_of(text), [])

    def test_second_target_opens_new_recipe(self):
        text = ("all: app\n"
                "\tgcc -o app app.o\n"
                "clean:\n"
                "  rm -f app\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 4)

    def test_pattern_rule_opens_recipe(self):
        bad = findings_of("%.o: %.c\n    gcc -c $<\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)

    def test_phony_target_opens_recipe(self):
        bad = findings_of(".PHONY: clean\nclean:\n  rm -f app\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 3)

    def test_double_colon_rule_opens_recipe(self):
        bad = findings_of("all:: app\n    gcc -o app app.o\n")
        self.assertEqual(len(bad), 1)

    def test_target_specific_variable_is_a_target(self):
        text = ("all: CC = gcc\n"
                "    gcc -o app app.o\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)

    def test_colon_equals_assignment_is_not_a_target(self):
        text = ("CC := gcc\n"
                "    not a recipe\n")
        self.assertEqual(findings_of(text), [])

    def test_question_equals_assignment_is_not_a_target(self):
        self.assertEqual(
            findings_of("CC ?= gcc\n    not a recipe\n"), [])

    def test_plus_equals_assignment_is_not_a_target(self):
        self.assertEqual(
            findings_of("FLAGS += -O2\n    not a recipe\n"), [])

    def test_empty_file_passes(self):
        self.assertEqual(findings_of(""), [])

    def test_file_with_only_variables_passes(self):
        self.assertEqual(
            findings_of("CC = gcc\nCFLAGS = -Wall\n"), [])

    def test_file_with_only_comments_passes(self):
        self.assertEqual(
            findings_of("# a comment\n# another\n"), [])

    def test_semicolon_recipe_on_target_line_passes(self):
        self.assertEqual(
            findings_of("all: app; gcc -o app app.o\n"), [])

    def test_backslash_continuation_line_not_checked(self):
        text = ("FLAGS = -Wall \\\n"
                "    -O2\n")
        self.assertEqual(findings_of(text), [])

    def test_backslash_continued_recipe_line_not_checked(self):
        text = ("all: app\n"
                "\tgcc -o app app.o \\\n"
                "    -lm\n")
        self.assertEqual(findings_of(text), [])

    def test_backslash_continued_target_line_not_checked(self):
        text = ("all: app \\\n"
                "    util.o\n"
                "\tgcc -o app app.o util.o\n")
        self.assertEqual(findings_of(text), [])

    def test_define_block_skipped(self):
        text = ("define GREETING\n"
                "\techo hello\n"
                "    echo spaces\n"
                "endef\n"
                "all: app\n"
                "\ttrue\n")
        self.assertEqual(findings_of(text), [])

    def test_tab_recipe_inside_define_not_stray(self):
        text = ("define GREETING\n"
                "\techo hello\n"
                "endef\n")
        self.assertEqual(findings_of(text), [])

    def test_indented_comment_in_recipe_is_a_recipe(self):
        # A tab-indented line starting with # is a shell
        # comment inside the recipe, not a Makefile comment.
        self.assertEqual(
            findings_of("all: app\n\t# a shell comment\n"), [])


class TestCLI(unittest.TestCase):
    def test_clean_file_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "Makefile", "all: app\n\ttrue\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("every recipe line starts with a tab", out)
            self.assertEqual(err, "")

    def test_flagged_file_exit_1_with_file_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "Makefile", "all: app\n    true\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("line 2", out)
            self.assertIn("missing separator", out)
            self.assertIn(path, out)

    def test_folder_walk_finds_makefiles_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "Makefile", "all: app\n\ttrue\n")
            write(tmp, "build.mk", "all: app\n    true\n")
            write(tmp, "notes.txt", "all: app\n    true\n")
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)
            self.assertIn("build.mk", out)
            self.assertNotIn("notes.txt", out)

    def test_folder_walk_finds_makefile_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "makefile", "all: app\n\ttrue\n")
            write(tmp, "GNUmakefile", "all: app\n\ttrue\n")
            write(tmp, "rules.mak", "all: app\n\ttrue\n")
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("3 file(s) checked", out)

    def test_folder_walk_skips_nested_with_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "Makefile", "all: app\n\ttrue\n")
            write(tmp, "sub/Makefile", "all: app\n    true\n")
            code, out, err = run_cli([tmp, "--no-recursive"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)

    def test_exclude_skips_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "Makefile", "all: app\n\ttrue\n")
            write(tmp, "build.mk", "all: app\n    true\n")
            code, out, err = run_cli([tmp, "--exclude", "build.mk"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_git_folder_skipped_in_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "Makefile", "all: app\n\ttrue\n")
            write(tmp, ".git/Makefile", "all: app\n    true\n")
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "build.txt", "all: app\n    true\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("build.txt", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "Makefile", "all: app\n\ttrue\n")
            code, out, err = run_cli([path, path])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "Makefile", "all: app\n    true\n")
            code, out, err = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["path"], path)
            self.assertEqual(
                data["files"][0]["findings"][0]["line"], 2)
            self.assertIn("missing separator",
                          data["files"][0]["findings"][0]["reason"])
            self.assertIsNone(data["files"][0]["error"])

    def test_stdin_clean(self):
        result = subprocess.run(
            [sys.executable, str(SRC), "--stdin"],
            input="all: app\n\ttrue\n",
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("every recipe line starts with a tab",
                      result.stdout)

    def test_stdin_dirty(self):
        result = subprocess.run(
            [sys.executable, str(SRC), "--stdin"],
            input="all: app\n    true\n",
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL <stdin>: line 2", result.stdout)

    def test_stdin_with_paths_is_usage_error(self):
        code, out, err = run_cli(["--stdin", "Makefile"])
        self.assertEqual(code, 2)

    def test_no_paths_is_usage_error(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_exit_2(self):
        code, out, err = run_cli(["/nonexistent/path/xyz"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no Makefile found", err)

    def test_bad_flag_exit_2(self):
        code, out, err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("makefile_tab_checker 1.0.0", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "Makefile", b"\xff\xfeall: app\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "Makefile", "all: app\n    true\n")
            before = Path(path).read_text()
            run_cli([path])
            self.assertEqual(Path(path).read_text(), before)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "Makefile", "all: app\n\ttrue\n")
            result = subprocess.run(
                [sys.executable, str(SRC), "Makefile"],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("every recipe line starts with a tab",
                          result.stdout)

    def test_cli_runs_under_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "Makefile", "all: app\n\ttrue\n")
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                code, out, err = run_cli([path])
            finally:
                if old_home is None:
                    del os.environ["HOME"]
                else:
                    os.environ["HOME"] = old_home
            self.assertEqual(code, 0)


class TestExamples(unittest.TestCase):
    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        expected = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        clean = subprocess.run(
            [sys.executable, "src/makefile_tab_checker.py",
             "examples/clean.mk"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn(clean.stdout.strip(), readme)
        flagged = subprocess.run(
            [sys.executable, "src/makefile_tab_checker.py",
             "examples/flagged.mk"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(flagged.returncode, 1)
        self.assertIn(flagged.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/makefile_tab_checker.py",
             "examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 3 file(s), 2 recipe line(s) with the "
                      "wrong indent in 1 file(s).", folder.stdout)
        self.assertIn("Checked 3 file(s), 2 recipe line(s) with the "
                      "wrong indent in 1 file(s).", readme)
        edge = subprocess.run(
            [sys.executable, "src/makefile_tab_checker.py",
             "examples/edge.mk"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(edge.returncode, 0)
        self.assertIn(edge.stdout.strip(), readme)
        js = subprocess.run(
            [sys.executable, "src/makefile_tab_checker.py",
             "--json", "examples/flagged.mk"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True, skip_examples=True):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")
                       and not (skip_tests and d == "tests")
                       and not (skip_examples and d == "examples")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for marker in ("/tmp/", "/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_no_real_secrets_outside_tests_and_examples(self):
        patterns = [
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
            re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
            re.compile(r"AIza[0-9A-Za-z_-]{35}"),
            re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"),
            re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ"),
        ]
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append("%s: %s" % (path.name, pattern.pattern))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src/makefile_tab_checker.py",
                       REPO / "tests/test_makefile_tab_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"makefile_tab_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src/makefile_tab_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_makefile_tab_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("whitespace-checker-cli", readme)


if __name__ == "__main__":
    unittest.main()
