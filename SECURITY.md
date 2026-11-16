# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the Makefiles you point it at, and it never rewrites a file and never changes anything. It writes nothing except the report on standard output (and usage errors on standard error). It never fetches a URL and never runs a command from a Makefile — it only reads the text.

It only checks that recipe lines start with a tab. It never runs make, never builds anything, and never executes a recipe.

If you find a case where the tool rewrites a file, runs a command, or reports a pass for a Makefile with a space-indented recipe line, please open an issue describing the exact commands and input. Do not include any real secret in the report.
