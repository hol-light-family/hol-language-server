# hol-language-server

Static lookup for [HOL Light](https://github.com/jrh13/hol-light) sources. `hol_language_server_core/` parses source files and the files they load, and indexes their definitions. It does not run HOL Light.

## Development

`uv sync` creates `.venv` from `uv.lock`. `uv run pytest` runs the tests, and `uv run basedpyright` the type check. Both run in CI on every pull request. How the tests work and how to add one: [tests/README.md](tests/README.md).
