# hol-language-server

Static lookup for [HOL Light](https://github.com/jrh13/hol-light) sources. `hol_language_server_core/` parses source files and the files they load, and indexes their definitions. It does not run HOL Light.

## Install

Needs [uv](https://docs.astral.sh/uv/). From the checkout:

```sh
uv tool install -e .
```

This puts the `hol-language-server` command on PATH (in `~/.local/bin`). With `-e` it runs the checkout itself, so edits apply without reinstalling.

## Configuration

The server takes the non-REPL settings of vscode-hol-light as flags. Most setups need two:

- `--hol-path`: HOL Light directory (with `hol.ml`).
- `--workspace`: workspace root. For s2n-bignum, whose proofs use paths like `needs "arm/proofs/base.ml"`, point it at the s2n-bignum checkout.

If your project loads files from directories HOL Light finds through `load_path`, name them with `--load-path` or `$HOLLIGHT_LOAD_PATH`.

If your project wraps `needs`, `prove` or `new_definition` in commands of its own, name them with `--custom-import`, `--custom-theorem` and `--custom-definition`.

Full flag reference: [docs/configuration.md](docs/configuration.md).

## Language server

Hover (theorem statements, value types, modules), Go to Definition (including the file named by `needs "..."`, and HOL constants inside terms), completion of names, module members, and import paths, document and workspace symbols, and warnings on loaded files that cannot be found. Reference: [docs/lsp.md](docs/lsp.md).

It speaks LSP over stdio:

```sh
hol-language-server --hol-path /path/to/hol-light --workspace /path/to/s2n-bignum
```

## Editor extension

`editors/vscode/` is a minimal VS Code client: it starts the server above
over `.ml` and `.hl` files. It declares no language, so syntax highlighting
comes from vscode-hol-light or an OCaml extension. Needs
[Node.js](https://nodejs.org/) for packaging:

```sh
cd editors/vscode
npm ci
npx @vscode/vsce package
code --install-extension hol-language-server-0.1.0.vsix
```

Two settings, both under `holLanguageServer`: `command` (default
`hol-language-server`) and `args`, flags passed straight to the server, for
example `"args": ["--hol-path", "/path/to/hol-light", "--load-path", "lib"]`.
New server flags work without updating the extension, and `--workspace` is
unneeded: the server uses the editor's open folder. The server restarts on
its own when they change, or run `HOL Language Server: Restart`.

Running it alongside vscode-hol-light gives duplicate hovers and definitions,
so disable one of them.

## Development

`uv sync` creates `.venv` from `uv.lock`. `uv run python -m pytest` runs the tests, and `uv run basedpyright` the type check. Both run in CI on every pull request. How the tests work and how to add one: [tests/README.md](tests/README.md).
