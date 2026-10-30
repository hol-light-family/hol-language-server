# Tests

Run them with `uv run python -m pytest`. They need no HOL Light build: every test reads
the small example files in `examples/`. (Bare `uv run pytest` can pick up a
`pytest` outside the project environment, and the language server it spawns
then dies without its dependencies.)

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
- `lookups.py`: reads and checks the `goto`, `hover`, and `complete`
  comments of an example file (below).

- `examples/`: each file starts with a comment saying what it sets up and what
  the tests check in it.
    - `hol/`: stands in for a HOL Light directory (`hol.ml`, `kernel.ml`).
    - `project/`: a small workspace whose files load each other. Each file sets up a case: `main.ml` loads a file that does not exist, `dup.ml` defines the same name twice, `ctx.ml` uses names loaded only by the file that loads it, `conversions.ml` builds and uses conversions, `locals.ml` has `let ... in` names and function parameters, `constants.ml` defines HOL constants and uses them in terms, `bound.ml` binds the name of a constant in a term, `comment_defs.ml` defines a name for real next to a commented-out one, plus a name that exists only in a comment, `completion.ml` probes name and member completion with `complete` comments, and `completion_files.ml` probes import paths the same way.
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

## Looked-up names in the example file

A service example holds what Go to Definition, hover, and completion must
return in comments of its own. `check_lookup_comments` in `lookups.py`
checks them. Each of `test_local_names_follow_scope`,
`test_constants_in_terms_go_to_their_definition`,
`test_a_bound_variable_named_like_a_constant_goes_nowhere` and
`test_conversions_resolve_where_they_are_used` indexes its file
and calls it. `test_a_comment_definition_is_not_a_definition`,
`test_completion_offers_what_the_complete_comments_say`, and
`test_import_paths_offer_what_the_complete_comments_say` do the same
for `comment_defs.ml`, `completion.ml`, and `completion_files.ml`.
`test_hover_definition_and_symbols`
in `test_lsp_server.py` drives the `tactics.ml` ones end to end over LSP
(same-file targets only).

```ocaml
let USES = `2 divides_alt 4 /\ evens 4`;;

(* goto: divides_alt 4 => divides_alt n <=> *)
(* goto: fib n = +4 => nowhere *)
(* hover: fib n = +4 => none *)

let z = ADD_S;;
(* complete: let z = ADD_S => ADD_SYM:theorem ADD_SYM_ALT:theorem *)
```

- `(* goto: use => target *)` says Go to Definition on `use` jumps to
  `target`, or nowhere when `target` is `nowhere`.
- `(* hover: use => text *)` says hover on `use` shows `text`, or nothing
  when `text` is `none`. Longer markdown goes on the lines after `=>`.
- `(* complete: use => labels *)` says completion with the cursor after
  `use` offers exactly those items, in order, or nothing when the payload
  is `none`. Each item is written `label:kind`.
- `use` and `target` are the text where the name first occurs, plus `+skip`
  characters when the name is not at the start of it. `target` names a file
  as `text @path/from/examples` when it is not the file of the comment.
  For `complete`, the cursor sits after `use`, plus `+skip` characters.
- Each comment goes after the code it names. A use or target resolves
  to its first occurrence, which must be the code, not another comment.
- A completion probe is code too, so its binder is indexed and matches
  later probes. Keep binder names out of the prefixes under test.
- An import probe resolves: every `needs` string in `completion_files.ml`
  names a file that exists, or the workspace-wide tests see a missing load.

## Reported diagnostics in the example file

A service example can also hold what opening the file publishes:

```ocaml
needs "missing.ml";; (* diagnostic: "missing.ml" => File not found: missing.ml *)
```

- `(* diagnostic: use => message *)` says opening the file publishes
  exactly that diagnostic over `use`, whose own span is the range. The
  comments list every diagnostic the file publishes, in order.
- `check_lsp_diagnostics` in `test_lsp_server.py` checks them end to end
  over LSP. Severity and source are fixed in the driver. Warnings, other
  files, and edit cycles stay procedural assertions in the test.

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
