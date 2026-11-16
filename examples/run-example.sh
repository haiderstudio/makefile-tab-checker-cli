#!/bin/sh
# Run the checker over each example file and show the result.
# The flagged example fails on purpose, so each run is allowed to fail.
cd "$(dirname "$0")/.."
for f in examples/clean.mk examples/flagged.mk examples/edge.mk; do
  echo "== $f =="
  python3 src/makefile_tab_checker.py "$f" || true
  echo
done
echo "== examples/ : the whole folder =="
python3 src/makefile_tab_checker.py examples/ || true
