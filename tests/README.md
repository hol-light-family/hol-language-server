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
- `expectations.py`: reads and checks the `expect` comments of an example
  file (below).

- `examples/`: each file starts with a comment saying what it sets up and what
  the tests check in it.
    - `hol/`: stands in for a HOL Light directory (`hol.ml`, `kernel.ml`).
    - `project/`: a small workspace whose files load each other. Each file sets up a case: `main.ml` loads a file that does not exist, `dup.ml` defines the same name twice, `ctx.ml` uses names loaded only by the file that loads it, `conversions.ml` builds and uses conversions, `locals.ml` has `let ... in` names and function parameters, and `constants.ml` defines HOL constants and uses them in terms.
    - `definitions.ml`, `modules.ml`, `sources.ml`: single files for parser
      cases, with their expected results in `expect` comments. `sources.ml`
      checks where the source of each definition starts and ends.

## Expected results in the example file

A parser example holds what the parser must find in comments of its own,
so the input and the expected result are read together.
`test_parser_finds_what_the_expect_comments_say` in `test_core.py` checks
each file it lists.

```ocaml
let [a; b] = [1; 2];;
(* expect: a b *)

let TH = prove
 (`x = x`,
  REFL_TAC);;
(* expect: TH:theorem@4:1-6:13 *)

module M = struct let inner = 1;; end;;
(* expect: M.inner *)
(* expect module: M *)
```

- `(* expect: ... *)` lists the definitions found since the previous
  `expect` comment, in order, separated by spaces. Each is written
  `name[:kind][@start-end]`.
  - `name`: the full name, with its modules (`M.inner`).
  - `kind`: `theorem`, `definition` or `term`. Left out, it is `other`.
  - `@start-end`: where the whole item defining the name starts and ends,
    each `line:column`, both counted from 1 and the end inclusive, as an
    editor shows them. Left out, it is not checked.
- `(* expect module: ... *)` lists the modules found since the previous
  `expect module` comment, by full name.
- Together the comments list everything the parser finds in the file, in
  file order: a definition or module missing from them fails the test.
- After an item not ended by `;;`, the comment becomes part of that item's
  source, up to the next item. Write its `@start-end` there, or put the
  comment after the next item that ends with `;;`.

## Adding a test

Every test asserts the expected result: the number of definitions parsed, the
exact hover text, or the line and column Go to Definition jumps to. A test
that only checks that nothing crashes is not enough.

1. Give it an input. Add a file under `examples/`, starting with a comment
   that says what it tests. For a small case, pass the text straight to
   `parse_text`, or write a file under pytest's `tmp_path`.
2. A parser case: write the expected result into the file as `expect`
   comments, and add the file to the list in
   `test_parser_finds_what_the_expect_comments_say`.
3. Anything else: add a `test_` function to the file that covers that part
   (see Layout), and assert the exact expected output.

For behavior that is wanted but not supported yet, write the test with the
correct expected output and mark it `@pytest.mark.xfail(strict=True,
reason=...)`. `strict` makes the test fail once the behavior starts working, so
the marker gets removed then.

Other tests assert exact counts and positions in the shared example files, so
editing one of them can break those tests. A new file is usually safer.
