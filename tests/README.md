# Tests

Run them with `uv run pytest`. They need no HOL Light build: every test reads
the small example files in `examples/`.

## Layout

- `test_core.py`: the parser, the index (`database.py`), and the service
  lookups.
- `test_service.py`: the lookups behind editor features: positions, hover, go to
  definition, document and workspace symbols, and settings.
- `test_lsp_server.py`: starts `lsp_server.py` and talks to it over stdio as
  an editor would, end to end.
- `hol_server_paths.py`: paths to the example files, shared by the tests.

- `examples/`:
    - `hol/`: stands in for a HOL Light directory (`hol.ml`, `kernel.ml`).
    - `project/`: a small workspace whose files load each other. Each file sets up a case, noted in its comments: `main.ml` loads a file that does not exist, `dup.ml` defines the same name twice, and `ctx.ml` uses names loaded only by the file that loads it.
    - `definitions.hl`, `modules.hl`: single files for parser cases.

Every test asserts the expected result: the number of definitions parsed, the
exact hover text, or the line and column Go to Definition jumps to. A test
that only checks that nothing crashes is not enough.

## Adding a test

Every test asserts the expected result: the number of definitions parsed, the
exact hover text, or the line and column Go to Definition jumps to. A test
that only checks that nothing crashes is not enough.

1. Give it an input. Add a file under `examples/`, or for a small case pass
   the text straight to `parse_text`, or write a file under pytest's
   `tmp_path`.
2. Add a `test_` function to the file that covers that part (see Layout).
3. Assert the exact expected output.

Other tests assert exact counts and positions in the shared example files, so
editing one of them can break those tests. A new file is usually safer.
