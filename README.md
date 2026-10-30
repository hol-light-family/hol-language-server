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

If your project wraps `needs`, `prove` or `new_definition` in commands of its own, name them with `--custom-import`, `--custom-theorem` and `--custom-definition`.

Full flag reference: [docs/configuration.md](docs/configuration.md).

## Language server

Hover (theorem statements, value types, modules), Go to Definition (including the file named by `needs "..."`, and HOL constants inside terms), completion of names, module members, and import paths, document and workspace symbols, and warnings on loaded files that cannot be found. Reference: [docs/lsp.md](docs/lsp.md).

It speaks LSP over stdio:

```sh
hol-language-server --hol-path /path/to/hol-light --workspace /path/to/s2n-bignum
```

## Editor extension

`editors/vscode/` is the VS Code extension: syntax highlighting plus a client that starts the server above. Needs [Node.js](https://nodejs.org/) for packaging:

```sh
cd editors/vscode
npm ci
npm run package
code --install-extension hol-language-server-0.1.0.vsix
```

Then set `hol-light.path` to the HOL Light directory; the other `hol-light.*` settings mirror the [configuration](docs/configuration.md). The server restarts on its own when they change, or run `HOL Light: Restart Language Server`.

## Development

`uv sync` creates `.venv` from `uv.lock`. `uv run pytest` runs the tests, and `uv run basedpyright` the type check. Both run in CI on every pull request. How the tests work and how to add one: [tests/README.md](tests/README.md).
