#!/usr/bin/env python3
"""Language server for HOL Light (hol-language-server).

Static lookup over `.ml` and `.hl` files: completion, hover statements,
go to definition, and document and workspace symbols. It parses files and
the files they load, plus the core HOL Light sources. It evaluates nothing.
"""

import logging
import sys

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer
from pygls.uris import from_fs_path, to_fs_path

from hol_language_server_core.config import Settings, expand_root_paths, parse_settings, settings_from_options
from hol_language_server_core.service import Completion, HolLanguageService, SymbolInfo
from hol_language_server_core.text import Position as CorePosition, Range as CoreRange, TextDoc

logger = logging.getLogger(__name__)

MAX_WORKSPACE_SYMBOLS = 1000

_SYMBOL_KINDS = {
    "theorem": lsp.SymbolKind.Constant,
    "definition": lsp.SymbolKind.Function,
    "term": lsp.SymbolKind.Constant,
    "value": lsp.SymbolKind.Variable,
    "module": lsp.SymbolKind.Module,
}

_COMPLETION_KINDS = {
    "theorem": lsp.CompletionItemKind.Constant,
    "definition": lsp.CompletionItemKind.Function,
    "term": lsp.CompletionItemKind.Constant,
    "constant": lsp.CompletionItemKind.Constant,
    "value": lsp.CompletionItemKind.Variable,
    "module": lsp.CompletionItemKind.Module,
    "file": lsp.CompletionItemKind.File,
    "folder": lsp.CompletionItemKind.Folder,
}


def _fs_path(uri: str) -> str:
    path = to_fs_path(uri)
    if path is None:
        raise ValueError(f"Not a file URI: {uri}")
    return path


def _uri(path: str) -> str:
    uri = from_fs_path(path)
    if uri is None:
        raise ValueError(f"No file URI for {path}")
    return uri


def _warn(ls: LanguageServer, message: str) -> None:
    ls.window_show_message(lsp.ShowMessageParams(type=lsp.MessageType.Warning, message=message))


def _utf16_units(line: str, scalar: int) -> int:
    """UTF-16 code units in the first `scalar` characters of the line."""
    scalar = min(max(scalar, 0), len(line))
    if line.isascii():
        return scalar
    return sum(2 if ord(char) > 0xFFFF else 1 for char in line[:scalar])


def _scalar_from_utf16(line: str, units: int) -> int:
    """Code points in the first `units` UTF-16 code units of the line."""
    if line.isascii():
        return min(max(units, 0), len(line))
    points = 0
    for char in line:
        units -= 2 if ord(char) > 0xFFFF else 1
        if units < 0:
            break
        points += 1
    return points


def _core_position(doc: TextDoc, pos: lsp.Position) -> CorePosition:
    """The request position in code points, the core's coordinates."""
    if 0 <= pos.line < doc.line_count:
        character = _scalar_from_utf16(doc.line_at(pos.line), pos.character)
    else:
        character = pos.character
    return CorePosition(pos.line, character)


def _cached_doc(service: HolLanguageService, docs: dict[str, TextDoc], path: str) -> TextDoc:
    """The document, reading it once per cache."""
    if path not in docs:
        docs[path] = service.get_document(path)
    return docs[path]


def _to_lsp_position(pos: CorePosition, doc: TextDoc) -> lsp.Position:
    if 0 <= pos.line < doc.line_count:
        character = _utf16_units(doc.line_at(pos.line), pos.character)
    else:
        character = pos.character
    return lsp.Position(line=pos.line, character=character)


def _to_lsp_range(span: CoreRange, doc: TextDoc) -> lsp.Range:
    return lsp.Range(start=_to_lsp_position(span.start, doc), end=_to_lsp_position(span.end, doc))


def _to_completion_item(item: Completion, doc: TextDoc) -> lsp.CompletionItem:
    return lsp.CompletionItem(
        label=item.label,
        kind=_COMPLETION_KINDS[item.kind],
        documentation=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=item.documentation)
        if item.documentation is not None else None,
        sort_text=item.sort_text,
        commit_characters=item.commit_characters,
        text_edit=lsp.TextEdit(range=_to_lsp_range(item.edit_range, doc), new_text=item.label)
        if item.edit_range is not None else None,
    )


def _to_symbol_info(symbol: SymbolInfo, doc: TextDoc) -> lsp.SymbolInformation:
    end = symbol.end_position
    if end is None:
        end = symbol.position.translate(0, len(symbol.name))
    return lsp.SymbolInformation(
        name=symbol.name,
        kind=_SYMBOL_KINDS[symbol.kind],
        location=lsp.Location(
            uri=_uri(symbol.path),
            range=_to_lsp_range(CoreRange(symbol.position, end), doc),
        ),
        container_name=symbol.container,
    )


def create_server(service: HolLanguageService, settings: Settings,
                  workspace_fixed: bool) -> LanguageServer:
    server = LanguageServer(
        "hol-language-server",
        "0.1.0",
        text_document_sync_kind=lsp.TextDocumentSyncKind.Full,
    )

    # Files with missing-load warnings published, so they are cleared once fixed.
    published: set[str] = set()

    def index(ls: LanguageServer, file_path: str, full: bool) -> None:
        # Indexes the file and its dependencies, and underlines each load that
        # cannot be found, in the file and in every file it sees.
        service.index(file_path, full)
        for path, missing in service.missing_loads(file_path).items():
            if not missing and path not in published:
                continue
            doc = service.get_document(path)
            ls.text_document_publish_diagnostics(lsp.PublishDiagnosticsParams(
                uri=_uri(path),
                diagnostics=[
                    lsp.Diagnostic(
                        range=_to_lsp_range(load.range, doc),
                        message=f"File not found: {load.name}",
                        severity=lsp.DiagnosticSeverity.Warning,
                        source="hol-language-server",
                    )
                    for load in missing
                ],
            ))
            if missing:
                published.add(path)
            else:
                published.discard(path)

    def prepare(ls: LanguageServer, uri: str) -> TextDoc:
        # Unchanged files are not parsed again.
        file_path = _fs_path(uri)
        index(ls, file_path, True)
        return service.get_document(file_path)

    @server.feature(lsp.INITIALIZE)
    def on_initialize(ls: LanguageServer, params: lsp.InitializeParams) -> None:
        if not workspace_fixed:
            folders = params.workspace_folders or []
            if folders:
                settings.workspace = _fs_path(folders[0].uri)
            elif params.root_uri:
                settings.workspace = _fs_path(params.root_uri)
            elif params.root_path:
                settings.workspace = params.root_path
        # No options is fine; options that are not a valid settings object fail initialize.
        options = params.initialization_options or {}
        if isinstance(options, dict) and "hol-light" in options:
            options = options["hol-light"]
        updated = settings_from_options(options, settings)
        settings.hol_path = updated.hol_path
        settings.root_paths = updated.root_paths
        settings.auto_index = updated.auto_index
        settings.index_workspace = updated.index_workspace
        settings.custom_commands = updated.custom_commands
        # Here rather than in initialized, so a bad directory or root path fails initialize.
        service.database.index_base_hol_light_files(settings.hol_path, settings.custom_commands)
        expand_root_paths(settings)

    @server.feature(lsp.INITIALIZED)
    def on_initialized(ls: LanguageServer, params: lsp.InitializedParams) -> None:
        if settings.index_workspace:
            unresolved = service.index_workspace()
            if unresolved:
                names = sorted({dep.name for dep in unresolved})
                _warn(ls, f"Loads not found in the workspace: {', '.join(names)}")

    @server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
    def on_open(ls: LanguageServer, params: lsp.DidOpenTextDocumentParams) -> None:
        item = params.text_document
        service.open_document(_fs_path(item.uri), item.text)
        if settings.auto_index:
            index(ls, _fs_path(item.uri), False)

    @server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
    def on_change(ls: LanguageServer, params: lsp.DidChangeTextDocumentParams) -> None:
        uri = params.text_document.uri
        service.open_document(_fs_path(uri), params.content_changes[-1].text)
        if settings.auto_index:
            index(ls, _fs_path(uri), False)

    @server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
    def on_close(ls: LanguageServer, params: lsp.DidCloseTextDocumentParams) -> None:
        service.close_document(_fs_path(params.text_document.uri))

    @server.feature(lsp.TEXT_DOCUMENT_HOVER)
    def on_hover(ls: LanguageServer, params: lsp.HoverParams) -> lsp.Hover | None:
        doc = prepare(ls, params.text_document.uri)
        pos = _core_position(doc, params.position)
        found = service.hover(doc, pos)
        if found is None:
            return None
        markdown, word_range = found
        return lsp.Hover(
            contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=markdown),
            range=_to_lsp_range(word_range, doc) if word_range is not None else None,
        )

    @server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
    def on_definition(ls: LanguageServer, params: lsp.DefinitionParams) -> list[lsp.Location]:
        doc = prepare(ls, params.text_document.uri)
        pos = _core_position(doc, params.position)
        docs: dict[str, TextDoc] = {}
        return [
            lsp.Location(
                uri=_uri(target.path),
                range=_to_lsp_range(target.range, _cached_doc(service, docs, target.path)),
            )
            for target in service.definition(doc, pos)
        ]

    @server.feature(lsp.TEXT_DOCUMENT_COMPLETION, lsp.CompletionOptions(trigger_characters=["/", '"']))
    def on_completion(ls: LanguageServer, params: lsp.CompletionParams) -> list[lsp.CompletionItem]:
        doc = prepare(ls, params.text_document.uri)
        pos = _core_position(doc, params.position)
        return [_to_completion_item(item, doc) for item in service.completion(doc, pos)]

    @server.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    def on_document_symbol(ls: LanguageServer,
                           params: lsp.DocumentSymbolParams) -> list[lsp.SymbolInformation]:
        file_path = _fs_path(params.text_document.uri)
        index(ls, file_path, False)
        doc = service.get_document(file_path)
        return [_to_symbol_info(s, doc) for s in service.document_symbols(file_path)]

    @server.feature(lsp.WORKSPACE_SYMBOL)
    def on_workspace_symbol(ls: LanguageServer,
                            params: lsp.WorkspaceSymbolParams) -> list[lsp.SymbolInformation]:
        query = params.query.lower()
        symbols = service.search_symbols(lambda name: query in name.lower())
        docs: dict[str, TextDoc] = {}
        return [_to_symbol_info(s, _cached_doc(service, docs, s.path))
                for s in symbols[:MAX_WORKSPACE_SYMBOLS]]

    return server


def main(argv: list[str] | None = None) -> None:
    settings, workspace_fixed = parse_settings(argv, __doc__)
    service = HolLanguageService(settings)
    create_server(service, settings, workspace_fixed).start_io()


def cli() -> None:
    # The console script and `python lsp_server.py`: the entry point, so it configures logging.
    logging.basicConfig(stream=sys.stderr)
    main()


if __name__ == "__main__":
    cli()
