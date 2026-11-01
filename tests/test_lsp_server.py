"""End-to-end tests of the language server over stdio, speaking LSP."""

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from hol_language_server_core.text import TextDoc
from hol_server_paths import PROJECT
from lookups import complete_probes

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lsp_server.py")
TACTICS = os.path.join(PROJECT, "tactics.ml")

# The LSP numbers of the kinds `complete` comments name.
_COMPLETION_KIND_NUMBERS = {
    "definition": 3,
    "value": 6,
    "module": 9,
    "file": 17,
    "folder": 19,
    "theorem": 21,
    "term": 21,
    "constant": 21,
}


def uri(path: str) -> str:
    return "file://" + path


class LspClient:
    """Minimal JSON-RPC client over Content-Length framing."""

    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        assert proc.stdin is not None and proc.stdout is not None
        self.stdin = proc.stdin
        self.stdout = proc.stdout
        self.next_id = 0
        # Server notifications (no id) seen while waiting for responses.
        self.notifications: list[dict[str, Any]] = []

    def _read_message(self) -> dict[str, Any]:
        headers: dict[str, str] = {}
        while True:
            line = self.stdout.readline().decode("ascii")
            if line in ("\r\n", ""):
                break
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        body = self.stdout.read(int(headers["content-length"]))
        return json.loads(body)

    def _send(self, message: dict[str, Any]) -> None:
        body = json.dumps(message).encode("utf-8")
        self.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.stdin.flush()

    def call(self, method: str, params: object) -> dict[str, Any]:
        """The response message, result or error."""
        self.next_id += 1
        self._send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        while True:
            message = self._read_message()
            if "id" not in message:
                self.notifications.append(message)
            elif message["id"] == self.next_id:
                return message

    def request(self, method: str, params: object) -> Any:
        message = self.call(method, params)
        assert "error" not in message, message["error"]
        return message["result"]

    def warnings(self) -> list[str]:
        return [n["params"]["message"] for n in self.notifications
                if n["method"] == "window/showMessage" and n["params"]["type"] == 2]

    def diagnostics(self, path: str) -> list[dict[str, Any]] | None:
        """The diagnostics last published for the file, or None if none were."""
        published = [n["params"]["diagnostics"] for n in self.notifications
                     if n["method"] == "textDocument/publishDiagnostics" and n["params"]["uri"] == uri(path)]
        return published[-1] if published else None

    def notify(self, method: str, params: object) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})


@contextmanager
def start_server(hol: str, workspace: str = PROJECT) -> Iterator[tuple[LspClient, Any]]:
    proc = subprocess.Popen(
        [sys.executable, SERVER, "--hol-path", hol, "--workspace", workspace],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    client = LspClient(proc)
    try:
        result = client.request(
            "initialize",
            {
                "processId": None,
                "rootUri": None,
                "capabilities": {},
                "workspaceFolders": None,
            },
        )
        client.notify("initialized", {})
        yield client, result
    finally:
        try:
            client.request("shutdown", None)
        except Exception:
            pass
        client.notify("exit", None)
        client.stdin.close()
        proc.wait(timeout=30)


_LOOKUP_RE = re.compile(r"\(\* (goto|hover): (.*?) =>\s+(.*?)\s+\*\)", re.DOTALL)


def _parse_use(raw: str) -> tuple[str, int]:
    """The snippet and the skip past it, as in `lookups.py`."""
    text, plus, skip = raw.strip().rpartition(" +")
    if plus and skip.isdigit():
        return text, int(skip)
    return raw.strip(), 0


def check_lsp_lookup_comments(client: LspClient, path: str, text: str) -> None:
    """Every goto and hover comment in the file holds over LSP.

    The same comment format `lookups.py` checks at the service level,
    driven through real hover and definition requests instead. The file
    must already be open, and every target must be in this file: a
    target elsewhere stays a hardcoded assertion in the test.
    """
    doc = TextDoc(path, text)
    for match in _LOOKUP_RE.finditer(text):
        kind, use_raw, payload_raw = match.group(1), match.group(2), match.group(3)
        snippet, skip = _parse_use(use_raw)
        offset = text.index(snippet) + skip
        assert offset < match.start(), f"{snippet!r} first occurs inside or after its comment"
        position = doc.position_at(offset)
        params = {
            "textDocument": {"uri": uri(path)},
            "position": {"line": position.line, "character": position.character},
        }
        if kind == "goto":
            if payload_raw.strip() == "nowhere":
                assert client.request("textDocument/definition", params) == []
                continue
            target, target_skip = _parse_use(payload_raw)
            [found] = client.request("textDocument/definition", params)
            expected = doc.position_at(text.index(target) + target_skip)
            assert found["uri"] == uri(path)
            assert (found["range"]["start"]["line"], found["range"]["start"]["character"]) == (
                expected.line,
                expected.character,
            )
        elif payload_raw.strip() == "none":
            assert client.request("textDocument/hover", params) is None
        else:
            hover = client.request("textDocument/hover", params)
            assert hover is not None
            assert hover["contents"]["value"] == payload_raw.strip()


def check_lsp_complete_comments(client: LspClient, path: str, text: str) -> None:
    """Every complete comment in the file holds over LSP. The file must already be open."""
    doc = TextDoc(path, text)
    for offset, expected in complete_probes(text):
        position = doc.position_at(offset)
        items = client.request(
            "textDocument/completion",
            {"textDocument": {"uri": uri(path)},
             "position": {"line": position.line, "character": position.character}},
        )["items"]
        assert [(item["label"], item["kind"]) for item in items] == [
            (label, _COMPLETION_KIND_NUMBERS[kind]) for label, kind in expected]


_DIAGNOSTIC_RE = re.compile(r"\(\* diagnostic: (.*?) =>\s+(.*?)\s+\*\)")


def check_lsp_diagnostics(client: LspClient, path: str, text: str) -> None:
    """Every diagnostic comment in the file matches what the server publishes.

    The use snippet's own span is the expected range, so the comments list
    every diagnostic the file publishes, in order. The file must already
    be open; a documentSymbol request flushes past the published
    diagnostics over ordered stdio. Severity and source are fixed here.
    """
    doc = TextDoc(path, text)
    client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri(path)}})
    expected = []
    for match in _DIAGNOSTIC_RE.finditer(text):
        use_raw, message = match.group(1), match.group(2).strip()
        snippet, skip = _parse_use(use_raw)
        offset = text.index(snippet) + skip
        assert offset < match.start(), f"{snippet!r} first occurs inside or after its comment"
        start = doc.position_at(offset)
        end = doc.position_at(offset + len(snippet))
        expected.append(
            {
                "range": {
                    "start": {"line": start.line, "character": start.character},
                    "end": {"line": end.line, "character": end.character},
                },
                "message": message,
                "severity": 2,
                "source": "hol-language-server",
            }
        )
    assert client.diagnostics(path) == expected


def test_initialize_advertises_the_subset():
    from hol_server_paths import HOL

    with start_server(HOL) as (_, result):
        capabilities = result["capabilities"]
        assert capabilities["hoverProvider"] is True
        assert capabilities["definitionProvider"] is True
        assert capabilities["documentSymbolProvider"] is True
        assert capabilities["workspaceSymbolProvider"] == {"resolveProvider": False}
        assert capabilities["completionProvider"] == {"triggerCharacters": ["/", '"']}


def test_hover_definition_and_symbols():
    from hol_server_paths import HOL

    with start_server(HOL) as (client, _):
        with open(TACTICS, encoding="utf-8") as handle:
            text = handle.read()
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(TACTICS), "languageId": "ocaml", "version": 1, "text": text}},
        )
        check_lsp_lookup_comments(client, TACTICS, text)

        symbols = client.request(
            "textDocument/documentSymbol", {"textDocument": {"uri": uri(TACTICS)}}
        )
        assert {s["name"] for s in symbols} >= {"HELPER_TAC", "MY_TAC", "OTHER_TAC"}

        found = client.request("workspace/symbol", {"query": "helper"})
        assert [s["name"] for s in found] == ["HELPER_TAC"]

        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(TACTICS)}})


def test_word_binders_over_lsp():
    from hol_server_paths import HOL

    path = os.path.join(PROJECT, "word_binders.ml")
    with start_server(HOL) as (client, _):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1, "text": text}},
        )
        check_lsp_lookup_comments(client, path, text)
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


@pytest.mark.parametrize(
    "name", ["completion.ml", "completion_files.ml", "completion_unclosed_term.ml", "constants.ml", "word_binders.ml",
             "../load_path/main.ml"])
def test_completion_offers_what_the_complete_comments_say(name: str):
    from hol_server_paths import HOL

    path = os.path.join(PROJECT, name)
    with start_server(HOL) as (client, _):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1, "text": text}},
        )
        check_lsp_complete_comments(client, path, text)
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


@pytest.mark.parametrize(("name", "snippet", "start", "item"), [
    ("completion.ml", "let z = Kernel.kfun", 15, {"label": "kfun", "kind": 6}),
    ("completion_files.ml", 'needs "lib/util.ml', 11, {"label": "util.ml", "kind": 17, "sortText": " util.ml"}),
])
def test_completion_items_carry_their_edit(name: str, snippet: str, start: int, item: dict[str, Any]):
    from hol_server_paths import HOL

    path = os.path.join(PROJECT, name)
    with start_server(HOL) as (client, _):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1, "text": text}},
        )
        position = TextDoc(path, text).position_at(text.index(snippet) + len(snippet))
        found = client.request(
            "textDocument/completion",
            {"textDocument": {"uri": uri(path)},
             "position": {"line": position.line, "character": position.character}},
        )["items"][0]
        assert found == {**item, "textEdit": {
            "range": {"start": {"line": position.line, "character": start},
                      "end": {"line": position.line, "character": position.character}},
            "newText": item["label"]}}
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


def test_completion_leaves_loaded_files_to_the_other_requests(tmp_path: Path):
    from hol_server_paths import HOL

    loaded = tmp_path / "loaded.ml"
    loaded.write_text("let zz_one = 1;;\n", encoding="utf-8")
    path = str(tmp_path / "t.ml")
    text = 'needs "loaded.ml";;\nlet y = zz_'
    params = {"textDocument": {"uri": uri(path)}, "position": {"line": 1, "character": 11}}
    with start_server(HOL) as (client, _):
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1, "text": text}},
        )

        def labels() -> list[str]:
            return [item["label"] for item in client.request("textDocument/completion", params)["items"]]

        assert labels() == ["zz_one"]
        loaded.write_text("let zz_one = 1;;\nlet zz_two = 2;;\n", encoding="utf-8")
        stat = loaded.stat()
        os.utime(loaded, (stat.st_atime, stat.st_mtime + 10))
        # Completion does not look at the loaded file again; hover does.
        assert labels() == ["zz_one"]
        client.request("textDocument/hover", params)
        assert labels() == ["zz_one", "zz_two"]
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


def test_a_deleted_load_of_a_loaded_file_is_shown(tmp_path: Path):
    from hol_server_paths import HOL

    (tmp_path / "middle.ml").write_text('needs "last.ml";;\n', encoding="utf-8")
    last = tmp_path / "last.ml"
    last.write_text("let zz_last = 1;;\n", encoding="utf-8")
    path = str(tmp_path / "t.ml")
    text = 'needs "middle.ml";;\nlet y = zz_'
    params = {"textDocument": {"uri": uri(path)}, "position": {"line": 1, "character": 11}}
    with start_server(HOL) as (client, _):
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1, "text": text}},
        )
        last.unlink()
        # Hover and go to definition walk the loads: neither may fail on the gone file.
        client.request("textDocument/hover", params)
        [missing] = client.diagnostics(str(tmp_path / "middle.ml")) or []
        assert missing["message"] == "File not found: last.ml"
        last.write_text("let zz_last = 1;;\n", encoding="utf-8")
        client.request("textDocument/hover", params)
        assert client.diagnostics(str(tmp_path / "middle.ml")) == []
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


def test_load_path_updates_change_what_is_missing(tmp_path: Path):
    from hol_server_paths import HOL

    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "v.ml").write_text("let v = 1;;\n", encoding="utf-8")
    path = str(tmp_path / "t.ml")
    text = 'needs "v.ml";;\n'
    with start_server(HOL) as (client, _):
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1, "text": text}},
        )
        client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri(path)}})
        [missing] = client.diagnostics(path) or []
        assert missing["message"] == "File not found: v.ml"
        # Only the load path changes: the load's name is the same.
        client.notify(
            "textDocument/didChange",
            {"textDocument": {"uri": uri(path), "version": 2},
             "contentChanges": [{"text": 'load_path := "vendor" :: !load_path;;\n' + text}]},
        )
        client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri(path)}})
        assert client.diagnostics(path) == []
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


def test_the_environment_load_path_reaches_the_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from hol_server_paths import HOL

    (tmp_path / "extra").mkdir()
    (tmp_path / "extra" / "in_extra.ml").write_text("let in_extra = 1;;\n", encoding="utf-8")
    monkeypatch.setenv("HOLLIGHT_LOAD_PATH", str(tmp_path / "extra"))
    path = str(tmp_path / "t.ml")
    with start_server(HOL) as (client, _):
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1,
                              "text": 'needs "in_extra.ml";;\n'}},
        )
        client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri(path)}})
        assert not client.diagnostics(path)
        [target] = client.request(
            "textDocument/definition",
            {"textDocument": {"uri": uri(path)}, "position": {"line": 0, "character": 8}},
        )
        assert target["uri"] == uri(str(tmp_path / "extra" / "in_extra.ml"))
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


def test_load_path_diagnostics():
    from hol_server_paths import EXAMPLES, HOL

    path = os.path.join(EXAMPLES, "load_path", "main.ml")
    with start_server(HOL) as (client, _):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1, "text": text}},
        )
        check_lsp_diagnostics(client, path, text)
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


def test_a_symlink_cycle_does_not_stop_workspace_indexing(tmp_path: Path):
    from hol_server_paths import HOL

    (tmp_path / "good.ml").write_text("let found_me = 1;;\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "loop").symlink_to(tmp_path, target_is_directory=True)
    with start_server(HOL, str(tmp_path)) as (client, _):
        [found] = client.request("workspace/symbol", {"query": "found_me"})
        assert found["location"]["uri"] == uri(str(tmp_path / "good.ml"))


def test_definitions_in_comments_are_not_published():
    from hol_server_paths import HOL

    with start_server(HOL) as (client, _):
        with open(TACTICS, encoding="utf-8") as handle:
            text = handle.read()
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(TACTICS), "languageId": "ocaml", "version": 1, "text": text}},
        )
        symbols = client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri(TACTICS)}})
        # The goto comments name `let HELPER_TAC th` twice; the index
        # must not publish them.
        assert [s["name"] for s in symbols].count("HELPER_TAC") == 1
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(TACTICS)}})


def test_bad_settings_fail_initialize():
    proc = subprocess.Popen(
        [sys.executable, SERVER, "--workspace", PROJECT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={k: v for k, v in os.environ.items() if k != "HOL_LIGHT_DIR"},
    )
    client = LspClient(proc)
    try:
        for options, message in [
            ({"hol-light": {"holPath": "/hol"}}, "Unknown hol-light settings: holPath"),
            ({}, "No HOL Light directory"),
        ]:
            response = client.call(
                "initialize",
                {"processId": None, "rootUri": None, "capabilities": {},
                 "initializationOptions": options},
            )
            assert message in response["error"]["message"]
    finally:
        proc.kill()
        proc.wait(timeout=30)


def test_completion_converts_utf16_columns(tmp_path: Path):
    from hol_server_paths import HOL

    (tmp_path / "🙂dir").mkdir()
    (tmp_path / "🙂dir" / "x.ml").write_text("let x = 1;;\n", encoding="utf-8")
    path = str(tmp_path / "t.ml")
    # The cursor sits after `x`: UTF-16 column 14, code-point column 13.
    text = 'needs "🙂dir/x";;'
    with start_server(HOL) as (client, _):
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1, "text": text}},
        )
        [item] = client.request(
            "textDocument/completion",
            {"textDocument": {"uri": uri(path)}, "position": {"line": 0, "character": 14}},
        )["items"]
        assert item["label"] == "x.ml"
        assert item["textEdit"]["range"] == {
            "start": {"line": 0, "character": 13}, "end": {"line": 0, "character": 14}}
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


def test_completion_list_is_capped_and_marked_incomplete(tmp_path: Path):
    from hol_server_paths import HOL

    path = str(tmp_path / "many.ml")
    # 201 names start with `n`, more than the 200-item cap; 11 start with `n10`.
    text = "".join(f"let n{i} = {i};;\n" for i in range(201)) + "let z = n"
    with start_server(HOL) as (client, _):
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1, "text": text}},
        )
        capped = client.request(
            "textDocument/completion",
            {"textDocument": {"uri": uri(path)}, "position": {"line": 201, "character": 9}},
        )
        assert capped["isIncomplete"] is True
        assert len(capped["items"]) == 200
        client.notify(
            "textDocument/didChange",
            {"textDocument": {"uri": uri(path), "version": 2},
             "contentChanges": [{"text": text + "10"}]},
        )
        narrowed = client.request(
            "textDocument/completion",
            {"textDocument": {"uri": uri(path)}, "position": {"line": 201, "character": 11}},
        )
        assert narrowed["isIncomplete"] is False
        assert len(narrowed["items"]) == 11
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


def test_workspace_symbols_convert_columns_from_the_index(tmp_path: Path):
    from hol_server_paths import HOL

    path = tmp_path / "gone.ml"
    # The name starts at code-point column 12, UTF-16 column 13.
    text = "(* 🙂 *) let zz_gone = 1;;\n"
    path.write_text(text, encoding="utf-8")
    with start_server(HOL) as (client, _):
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(str(path)), "languageId": "ocaml", "version": 1, "text": text}},
        )
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(str(path))}})
        # Deleted after indexing: the index still holds it, and the columns
        # come from the index, not the file.
        path.unlink()
        [found] = client.request("workspace/symbol", {"query": "zz_gone"})
        assert found["location"]["range"] == {
            "start": {"line": 0, "character": 13}, "end": {"line": 0, "character": 20}}


def test_definition_converts_utf16_columns(tmp_path: Path):
    from hol_server_paths import HOL

    (tmp_path / "u.ml").write_text("(* 🙂 *) let foo = 1;;\n", encoding="utf-8")
    path = str(tmp_path / "t.ml")
    text = 'needs "u.ml";;\nlet z = foo;;\n'
    with start_server(HOL) as (client, _):
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(path), "languageId": "ocaml", "version": 1, "text": text}},
        )
        targets = client.request(
            "textDocument/definition",
            {"textDocument": {"uri": uri(path)}, "position": {"line": 1, "character": 10}},
        )
        [target] = [t for t in targets if t["uri"] == uri(str(tmp_path / "u.ml"))]
        assert target["range"] == {
            "start": {"line": 0, "character": 13}, "end": {"line": 0, "character": 13}}
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(path)}})


def test_unresolved_loads_are_shown():
    from hol_server_paths import HOL

    main = os.path.join(PROJECT, "main.ml")
    with start_server(HOL) as (client, _):
        with open(main, encoding="utf-8") as handle:
            text = handle.read()
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(main), "languageId": "ocaml", "version": 1, "text": text}},
        )
        check_lsp_diagnostics(client, main, text)
        assert client.warnings() == ["Loads not found in the workspace: missing.ml"]
        assert client.diagnostics(os.path.join(PROJECT, "lib", "util.ml")) is None
        # Fixing the load clears the warning.
        client.notify(
            "textDocument/didChange",
            {"textDocument": {"uri": uri(main), "version": 2},
             "contentChanges": [{"text": text.replace('needs "missing.ml";;', "")}]},
        )
        client.request("textDocument/documentSymbol", {"textDocument": {"uri": uri(main)}})
        assert client.diagnostics(main) == []
