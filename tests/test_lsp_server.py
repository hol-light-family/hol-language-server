"""End-to-end tests of the language server over stdio, speaking LSP."""

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from hol_language_server_core.text import TextDoc
from hol_server_paths import PROJECT

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lsp_server.py")
TACTICS = os.path.join(PROJECT, "tactics.ml")


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
def start_server(hol: str) -> Iterator[tuple[LspClient, Any]]:
    proc = subprocess.Popen(
        [sys.executable, SERVER, "--hol-path", hol, "--workspace", PROJECT],
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
        assert capabilities["completionProvider"] == {"triggerCharacters": ["/"]}


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


def test_completion_suggests_names_members_and_files():
    from hol_server_paths import HOL

    with start_server(HOL) as (client, _):
        with open(TACTICS, encoding="utf-8") as handle:
            text = handle.read()
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri(TACTICS), "languageId": "ocaml", "version": 1, "text": text}},
        )
        [found] = client.request(
            "textDocument/completion",
            {"textDocument": {"uri": uri(TACTICS)}, "position": {"line": 17, "character": 22}},
        )
        assert found == {"label": "HELPER_TAC", "kind": 6}
        # At the name being defined, nothing completes.
        assert (
            client.request(
                "textDocument/completion",
                {"textDocument": {"uri": uri(TACTICS)}, "position": {"line": 11, "character": 14}},
            )
            == []
        )

        changed = text + "let z = Kernel.kfun"
        client.notify(
            "textDocument/didChange",
            {"textDocument": {"uri": uri(TACTICS), "version": 2},
             "contentChanges": [{"text": changed}]},
        )
        members = client.request(
            "textDocument/completion",
            {"textDocument": {"uri": uri(TACTICS)},
             "position": {"line": text.count("\n"), "character": len("let z = Kernel.kfun")}},
        )
        assert [item["label"] for item in members] == ["kfun", "kfun2"]
        for item in members:
            edit = item["textEdit"]
            assert (edit["range"]["start"]["character"], edit["range"]["end"]["character"]) == (15, 19)
            assert edit["newText"] == item["label"]

        client.notify(
            "textDocument/didChange",
            {"textDocument": {"uri": uri(TACTICS), "version": 3},
             "contentChanges": [{"text": 'needs "lib/u'}]},
        )
        files = client.request(
            "textDocument/completion",
            {"textDocument": {"uri": uri(TACTICS)},
             "position": {"line": 0, "character": len('needs "lib/u')}},
        )
        assert {item["label"] for item in files} == {"util.ml"}
        assert files[0]["kind"] == 17
        assert files[0]["sortText"] == " util.ml"
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri(TACTICS)}})


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
