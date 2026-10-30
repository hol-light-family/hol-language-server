"""The parser: top-level statements, `let` bindings, and modules."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from hol_language_server_core.parser.lexer import (Lexer, LexerState, ParserError, Token, TokenType, end_position,
                                                   line_number)
from hol_language_server_core.parser.model import (CustomCommands, Definition, DefinitionType, Dependency, Module,
                                                   OpenDecl, ParseResult)
from hol_language_server_core.parser.terms import declared_infixes, term_constants
from hol_language_server_core.text import CHAR_LITERAL, Position, Range

logger = logging.getLogger(__name__)


def parse_text(text: str, file_path: str, custom: CustomCommands,
               infixes: frozenset[str] = frozenset()) -> ParseResult:
    """infixes: infix names declared outside the file (it may declare its own)."""
    return Parser(text, custom, infixes).parse(file_path)


def _skip_re(search_module_end: bool) -> re.Pattern[str]:
    words = "module|begin|end|let" if search_module_end else "module|let"
    return re.compile(
        CHAR_LITERAL + r"|\(\*|" + r'["`]|;;+|\b(?:' + words + r")\b"
    )


_SKIP_RE = {True: _skip_re(True), False: _skip_re(False)}


@dataclass
class Binding:
    name_token: Token
    type: str = ""


class Parser(Lexer):
    def __init__(self, text: str, custom: CustomCommands, infixes: frozenset[str] = frozenset()) -> None:
        super().__init__(text)

        def mk(words: list[str]) -> re.Pattern[str]:
            return re.compile("^(?:" + "|".join(words) + ")$")

        self._import_re = mk(["needs", "loads", "loadt", *custom.imports])
        self._theorem_re = mk(["prove", "VECTOR_ARITH", "ARITH_RULE", "REAL_ARITH", *custom.theorems])
        self._definition_re = mk(["new_definition", "new_basic_definition", "define", *custom.definitions])
        self._def_other_re = mk(["new_recursive_definition"])
        self._inductive_re = mk(["new_inductive_definition"])
        # Infix names, to find the head of `x IN s = ...`.
        self._infixes = declared_infixes(text) | infixes
        self._constants: list[Definition] = []

    def skip_to_next_statement(self, search_module_end: bool, item_indent: int) -> None:
        # The next call skips the current token. Do not check for `module`
        # and `end` here: a current `module` or `end` is handled by parse().
        # Skip comments first: the current token starts the statement.
        if self.next_skip_comments().type == TokenType.statement_separator:
            return
        # Not strictly necessary since next_token resets _cur.
        self._cur = None

        # With search_module_end, `end` tokens closing a module expression
        # are honored. Some modules hold no `;;`, and `end` is not always
        # followed by `;;`. Only `begin`/`end` pairs count: other `end`
        # closers (`sig`, `struct`, `object`) may hold `;;` and are skipped.
        # A `let` starting a line, indented no deeper than the current item,
        # and not opening a `let ... in` expression starts the next item.
        # Items are often not separated by `;;` inside modules (the kernel
        # in HOL Light's fusion.ml) and sometimes at the top level.
        pattern = _SKIP_RE[search_module_end]
        pos = self.pos
        begin_level = 0
        while True:
            m = pattern.search(self.text, pos)
            if m is None:
                break
            tok = m.group(0)
            pos = m.end()
            if tok.startswith("'"):
                # A character literal.
                continue
            if tok == "(*":
                self._parse_comment(m.start())
                pos = self.pos
            elif tok == '"':
                self._parse_string(m.start())
                pos = self.pos
            elif tok == "`":
                self._parse_term(m.start())
                pos = self.pos
            elif tok == "begin":
                begin_level += 1
            elif tok == "let":
                # lastIndexOf('\n', m.index - 1): the newline at or before the token.
                line_start = self.text.rfind("\n", 0, m.start()) + 1
                if (
                    not begin_level
                    and m.start() - line_start <= item_indent
                    and not self.text[line_start:m.start()].strip()
                    and not self._is_let_in_expression(m.start())
                ):
                    self.pos = m.start()
                    return
            elif tok == "end":
                if begin_level:
                    begin_level -= 1
                else:
                    self.pos = m.start()
                    return
            elif tok == "module":
                self.pos = m.start()
                return
            else:
                # Past the matched `;;`.
                self.pos = pos
                return
        self.pos = len(self.text)

    def _is_let_in_expression(self, pos: int) -> bool:
        """Whether the `let` at pos closes with an `in` before `;;`."""
        saved = self.save_state()
        self.pos = pos
        self._cur = None
        try:
            self.next_token()
            depth = 1
            while True:
                token = self.next_skip_comments()
                if (
                    token.type == TokenType.eof
                    or token.type == TokenType.statement_separator
                ):
                    return False
                if token.value == "let":
                    depth += 1
                elif token.value == "in" and depth - 1 == 0:
                    return True
                elif token.value == "in":
                    depth -= 1
        finally:
            self.reset_state(saved)

    def _parse_type(self, allow_comma: bool = False) -> str:
        def atom() -> str:
            result = ""
            token = self.next_skip_comments()
            if token.value == "(":
                inner = self._parse_type(True)
                self.expect(")")
                result = f"({inner})"
            elif token.type == TokenType.identifier:
                result = token.get_value(self.text)
            elif token.value == "'":
                token = self.expect(TokenType.identifier)
                result = "'" + token.get_value(self.text)
            while True:
                token = self.match1(TokenType.identifier)
                if token is None:
                    break
                result = result + " " + token.get_value(self.text)
            return result

        def compound_type() -> str:
            result: list[str] = []
            while True:
                result.append(atom())
                token = self.peek_skip_comments()
                if token.value in ("->", "*") or (allow_comma and token.value == ","):
                    self.next_token()
                    result.append(", " if token.value == "," else " " + token.value + " ")
                else:
                    break
            return "".join(result)

        return compound_type()

    def _parse_pattern(self, allow_constructor: bool) -> list[Binding]:
        def atom() -> list[Binding]:
            result: list[Binding]
            token = self.next_skip_comments()
            if token.value == "(":
                # ( pattern [: type] )
                token = self.peek_skip_comments()
                if token.value == ")":
                    # unit pattern
                    self.next_token()
                    result = []
                elif token.type == TokenType.operator:
                    # ( operator )
                    self.next_token()
                    result = [Binding(token)]
                    self.expect(")")
                else:
                    result = self._parse_pattern(True)
                    if self.match1(":"):
                        type_text = self._parse_type()
                        if len(result) == 1 and not result[0].type:
                            # A pattern with a single name is just a simple pattern.
                            result[0].type = type_text
                    self.expect(")")
            elif token.value == "[" or token.value == "[|":
                # list or array of patterns
                end_value = "|]" if token.value == "[|" else "]"
                result = self._parse_pattern(True)
                while self.match1(";"):
                    if self.peek_skip_comments().value == end_value:
                        break
                    result.extend(self._parse_pattern(True))
                self.expect(end_value)
            elif token.value == "{":
                # record pattern
                result = record_field()
                while self.match1(";"):
                    token = self.peek_skip_comments()
                    if token.value == "_":
                        self.next_token()
                        self.match1(";")
                        break
                    if token.value == "}":
                        break
                    result.extend(record_field())
                self.expect("}")
            elif token.type == TokenType.identifier:
                # identifier
                result = [] if token.value == "_" else [Binding(token)]
                first = token.get_value(self.text)[:1]
                if allow_constructor and first.isupper() and first.isascii():
                    # constructor?
                    token = self.peek_skip_comments()
                    if token.type == TokenType.identifier:
                        # constructor with one argument
                        self.next_token()
                        result = [] if token.value == "_" else [Binding(token)]
                    elif (token.value or "") in ("(", "[", "{"):
                        # constructor with a pattern
                        result = self._parse_pattern(False)
            else:
                raise ParserError("identifier, (, or [ expected", token)
            return result

        def record_field() -> list[Binding]:
            field = self.next_skip_comments()
            if field.type != TokenType.identifier:
                raise ParserError("field name: identifier expected", field)
            result = [Binding(field)]
            if self.match1(":"):
                result[0].type = self._parse_type()
            if self.match1("="):
                return self._parse_pattern(True)
            return result

        def cons() -> list[Binding]:
            result: list[Binding] = []
            while True:
                result.extend(atom())
                if self.peek_skip_comments().value != "::":
                    break
                self.next_token()
            return result

        def tup() -> list[Binding]:
            result: list[Binding] = []
            while True:
                result.extend(cons())
                if self.match1("as"):
                    self.expect(TokenType.identifier)
                if self.peek_skip_comments().value != ",":
                    break
                self.next_token()
            return result

        return tup()

    def _skip_to_closing_bracket(self) -> None:
        """Skip tokens until an unmatched `)` (not consumed)."""
        depth = 0
        while True:
            token = self.peek_skip_comments()
            if token.type == TokenType.eof or token.type == TokenType.statement_separator:
                return
            if token.value == ")" and depth == 0:
                return
            if token.value in ("(", "[", "[|", "{"):
                depth += 1
            elif token.value in (")", "]", "|]", "}"):
                depth -= 1
            self.next_token()

    def _parse_parameter(self) -> list[Binding]:
        token = self.peek_skip_comments()
        if token.value == "~":
            # Labeled parameters.
            self.next_token()
            if self.match1("("):
                name_token = self.expect(TokenType.identifier)
                type_text = ""
                if self.match1(":"):
                    type_text = self._parse_type()
                self.expect(")")
            else:
                name_token = self.expect(TokenType.identifier)
                type_text = ""
                if self.match1(":"):
                    return self._parse_pattern(False)
            return [Binding(name_token, type_text)]
        if token.value == "?":
            # Optional parameters.
            self.next_token()
            if self.match1("("):
                name_token = self.expect(TokenType.identifier)
                type_text = ""
                if self.match1(":"):
                    type_text = self._parse_type()
                if self.match1("="):
                    # A default value: skip the expression.
                    self._skip_to_closing_bracket()
                self.expect(")")
            else:
                name_token = self.expect(TokenType.identifier)
                type_text = ""
                if self.match1(":"):
                    if self.match1("("):
                        # [:typexpr][= expr] is not supported.
                        result = self._parse_pattern(True)
                        self.expect(")")
                        return result
                    return self._parse_pattern(False)
            return [Binding(name_token, type_text)]
        return self._parse_pattern(False)

    def _parse_let_binding_lhs(self) -> list[Binding]:
        """Left hand side of a let binding (`=` not included, may be missing)."""
        result = self._parse_pattern(False)
        types: list[str] = []
        while True:
            token = self.peek_skip_comments()
            if token.value == ":" or token.value == "=":
                break
            par = self._parse_parameter()
            if len(par) == 1 and par[0].type:
                types.append(par[0].type)
            else:
                types.append("?")
        if token.value == ":":
            self.next_token()
            type_text = self._parse_type()
            if len(result) == 1 and not result[0].type:
                types.append(type_text)
                result[0].type = " -> ".join(
                    f"({t})" if "->" in t else t for t in types
                )
        return result

    def _parse_type_params(self) -> None:
        def type_param() -> None:
            token = self.next_skip_comments()
            if (token.value or "") in ("+", "-", "+!", "-!", "!-", "!+"):
                token = self.next_token()
            if token.value != "'":
                raise ParserError("' expected", token)
            self.expect(TokenType.identifier)

        if self.match1("("):
            while True:
                type_param()
                if not self.match1(","):
                    break
        else:
            type_param()

    def _parse_extended_module_path(self) -> str:
        result = ""
        while True:
            token = self.expect(TokenType.identifier)
            result += token.get_value(self.text)
            token = self.peek_skip_comments()
            if token.value == "(":
                self.next_token()
                inner = self._parse_extended_module_path()
                self.expect(")")
                result += f"({inner})"
            elif token.value == ".":
                result += "."
            else:
                break
        return result

    def _parse_mod_constraint(self) -> None:
        token = self.next_skip_comments()
        if token.value == "type":
            token = self.peek_skip_comments()
            if (token.value or "") in ("+", "-", "+!", "-!", "!-", "!+", "'", "("):
                self._parse_type_params()
            # should be [extended-module-path.]typeconst-name
            self._parse_extended_module_path()
            self.expect("=")
            self._parse_type()
            if self.match1("constraint"):
                self._parse_type()
                self.expect("=")
                self._parse_type()
        elif token.value == "module":
            self.expect(TokenType.identifier)
            self.expect("=")
            self._parse_extended_module_path()
        else:
            raise ParserError("type or module expected", token)

    def _parse_module_type(self) -> None:
        """Parses module types. Currently, does not return anything."""
        token = self.peek_skip_comments()
        if token.value == "(":
            self.next_token()
            self._parse_module_type()
            self.expect(")")
        elif token.value == "sig":
            self.next_token()
            # Skip until `end`.
            while True:
                token = self.next_skip_comments()
                if token.type == TokenType.eof or token.value == "end":
                    break
        elif token.value == "functor":
            raise ParserError("Functors are not supported", token)
        elif token.type == TokenType.identifier:
            self._parse_extended_module_path()
        else:
            raise ParserError("Module type expected", token)
        if self.match1("with"):
            while True:
                self._parse_mod_constraint()
                if not self.match1("and"):
                    break

    def _parse_module_expr(self) -> bool:
        """Parses a module expr. Only the start of `struct` is consumed."""
        token = self.next_skip_comments()
        if token.value == "struct":
            return True
        if token.value == "(":
            inner = self._parse_module_expr()
            if inner:
                # Closing ')' is not consumed (silently ignored after the end).
                return inner
            if self.match1(":"):
                self._parse_module_type()
            self.expect(")")
        elif token.value == "functor":
            self.expect("(")
            self.expect(TokenType.identifier)
            self.expect(":")
            self._parse_module_type()
            self.expect(")")
            self.expect("->")
            return self._parse_module_expr()
        elif token.type != TokenType.identifier:
            raise ParserError("Unsupported module expression", token)
        if self.match1("("):
            inner = self._parse_module_expr()
            if inner:
                return inner
            self.expect(")")
        return False

    def _parse_module_definition(self) -> Token | None:
        """`module` is already consumed. Returns the name token for `struct`."""
        if self.match1("type"):
            self.expect(TokenType.identifier)
            self.expect("=")
            self._parse_module_type()
            return None
        name_token = self.expect(TokenType.identifier)
        token = self.next_skip_comments()
        if token.value == "(":
            self.expect(TokenType.identifier)
            self.expect(":")
            self._parse_module_type()
            self.expect(")")
            token = self.next_skip_comments()
        if token.value == ":":
            self._parse_module_type()
            token = self.next_skip_comments()
        if token.value != "=":
            raise ParserError("= expected after a module declaration", token)
        return name_token if self._parse_module_expr() else None

    def _find_top_level_ands(self) -> list[LexerState]:
        """States after each `and` starting a new binding of this `let`.

        Finds `and` tokens not nested in brackets, `begin ... end`, or inner
        `let ... in` expressions. The parser state is not changed.
        """
        saved = self.save_state()
        result: list[LexerState] = []
        depth = 0
        let_depth = 0
        while True:
            token = self.next_skip_comments()
            if token.type == TokenType.eof or token.type == TokenType.statement_separator:
                break
            value = token.value or ""
            if value in ("(", "[", "[|", "{", "begin", "struct", "sig", "object"):
                depth += 1
            elif value in (")", "]", "|]", "}", "end"):
                depth -= 1
                if depth < 0:
                    break
            elif value == "let":
                let_depth += 1
            elif value == "in":
                let_depth = max(0, let_depth - 1)
            elif value == "and":
                if depth == 0 and let_depth == 0:
                    result.append(self.save_state())
        self.reset_state(saved)
        return result

    def _add_definition(self, uri: str, definitions: list[Definition],
                        module_stack: list[Module], name: str, def_type: DefinitionType,
                        content: str, offset: int, position: Position) -> None:
        module = module_stack[-1] if module_stack else None
        definitions.append(
            Definition(name, def_type, content, module, offset, uri, position)
        )

    def _add_constants(self, uri: str, name: str, token: Token, inductive: bool) -> None:
        """Record the constants that the definition `name`'s term token introduces."""
        if token.type != TokenType.term:
            return
        term = token.get_value(self.text)[1:-1]
        for constant, at in term_constants(term, self._infixes, inductive):
            offset = token.start_pos + 1 + at
            line = line_number(self._line_starts, offset)
            found = Definition(constant, DefinitionType.constant, term, None, offset, uri,
                               Position(line, offset - self._line_starts[line]))
            found.defined_by = name
            self._constants.append(found)

    def _parse_binding(self, uri: str, definitions: list[Definition],
                       module_stack: list[Module]) -> None:
        """Classifies one binding of the current `let`."""
        lhs = self._parse_let_binding_lhs()
        # `let R_RULES, R_INDUCT, R_CASES = new_inductive_definition `...``.
        state = self.save_state()
        if lhs and self.next_skip_comments().value == "=":
            self._skip_while_eq("(")
            if self._inductive_re.match(self.next_skip_comments().value or ""):
                self._skip_while_eq("(")
                self._add_constants(uri, lhs[0].name_token.get_value(self.text),
                                    self.next_skip_comments(), True)
        self.reset_state(state)
        if len(lhs) == 1 and self.next_skip_comments().value == "=":
            name = lhs[0].name_token.get_value(self.text)
            pos = lhs[0].name_token.start_pos
            position = lhs[0].name_token.get_start_position(self._line_starts)
            self._skip_while_eq("(")
            token = self.next_skip_comments()
            # `time f x` evaluates `f x` (e.g., `let TH = time prove(...)`).
            if token.value == "time":
                self._skip_while_eq("(")
                token = self.next_skip_comments()
            if token.type == TokenType.term:
                self._add_definition(
                    uri, definitions, module_stack,
                    name, DefinitionType.term,
                    token.get_value(self.text)[1:-1], pos, position,
                )
                return
            value = token.value or ""
            if self._theorem_re.match(value):
                self._skip_while_eq("(")
                # Accept terms, strings, and identifiers.
                token = self.next_skip_comments()
                if token.type in (TokenType.term, TokenType.string):
                    text = token.get_value(self.text)[1:-1]
                    self._add_definition(uri, definitions, module_stack,
                                         name, DefinitionType.theorem, text, pos, position)
                    return
                if token.type == TokenType.identifier:
                    self._add_definition(
                        uri, definitions, module_stack,
                        name, DefinitionType.theorem,
                        token.get_value(self.text), pos, position,
                    )
                    return
                if token.type != TokenType.statement_separator:
                    # `;;` here is an alias for a theorem-producing function.
                    self._report(f"Unparsed theorem: {name}", pos, uri)
            elif self._definition_re.match(value):
                self._skip_while_eq("(")
                token = self.next_skip_comments()
                self._add_constants(uri, name, token, False)
                if token.type in (TokenType.term, TokenType.string):
                    text = token.get_value(self.text)[1:-1]
                    self._add_definition(uri, definitions, module_stack,
                                         name, DefinitionType.definition, text, pos, position)
                    return
                if token.type == TokenType.identifier:
                    self._add_definition(
                        uri, definitions, module_stack,
                        name, DefinitionType.definition,
                        token.get_value(self.text), pos, position,
                    )
                    return
                if token.type != TokenType.statement_separator:
                    self._report(f"Unparsed definition: {name}", pos, uri)
            elif self._def_other_re.match(value):
                # Skip the next token.
                self.next_token()
                self._skip_while_eq("(")
                token = self.next_skip_comments()
                self._add_constants(uri, name, token, False)
                if token.type in (TokenType.term, TokenType.string):
                    text = token.get_value(self.text)[1:-1]
                    self._add_definition(uri, definitions, module_stack,
                                         name, DefinitionType.definition, text, pos, position)
                    return
                if token.type == TokenType.identifier:
                    self._add_definition(
                        uri, definitions, module_stack,
                        name, DefinitionType.definition,
                        token.get_value(self.text), pos, position,
                    )
                    return
                self._report(f"Unparsed definition(2): {name}", pos, uri)
        # Default case.
        for binding in lhs:
            name = binding.name_token.get_value(self.text)
            pos = binding.name_token.start_pos
            position = binding.name_token.get_start_position(self._line_starts)
            self._add_definition(uri, definitions, module_stack,
                                 name, DefinitionType.other, binding.type, pos, position)

    def _parse_let_statement(self, uri: str, definitions: list[Definition],
                             module_stack: list[Module]) -> None:
        """`let` is already consumed. Records the bindings it defines."""
        if self.peek_skip_comments().value == "rec":
            self.next_token()
        # `let a = ... and b = ...`: states after each top-level `and`.
        and_states = self._find_top_level_ands()
        self._parse_binding(uri, definitions, module_stack)
        for and_state in and_states:
            self.reset_state(and_state)
            try:
                self._parse_binding(uri, definitions, module_stack)
            except ParserError as err:
                self._report(f"Error: {err}", err.token, uri)

    def _scan_imports(self, dependencies: list[Dependency]) -> None:
        """Record every import call with its string argument, wherever it sits."""
        state = self.save_state()
        prev: Token | None = None
        while True:
            token = self.next_token()
            if token.type == TokenType.eof:
                break
            if (
                prev is not None
                and prev.type == TokenType.identifier
                and self._import_re.match(prev.value or "")
                and token.type == TokenType.string
                # Skip very long strings: most definitely invalid
                # (probably not properly closed yet).
                and token.end_pos - token.start_pos <= 2000
            ):
                text = token.get_value(self.text)[1:-1]
                # Ignore multiline strings: legal OCaml, but a path
                # with a newline never resolves to a file.
                if "\n" not in text:
                    dependencies.append(
                        Dependency(
                            text,
                            (prev.value or "") == "loads",
                            Range(
                                token.get_start_position(self._line_starts),
                                token.get_end_position(self._line_starts),
                            ),
                        )
                    )
            prev = token
        self.reset_state(state)

    def parse(self, uri: str) -> ParseResult:
        self.pos = 0
        self._cur = None
        self._constants = []

        global_module = Module("", None, 0, uri, Position(0, 0))
        definitions: list[Definition] = []
        dependencies: list[Dependency] = []
        modules: list[Module] = []
        module_stack: list[Module] = []

        # Imports sit anywhere in a statement (`then loads "x"`), so they get their own scan.
        self._scan_imports(dependencies)

        while self.peek().type != TokenType.eof:
            # Save and restore the state at the end of the loop: parsing may
            # consume a statement separator, which must not be skipped.
            # (For example, `let x;;` consumes its own `;;`.)
            state = self.save_state()

            # Safe to consume: the position is restored from `state`.
            statement_token = self.next_skip_comments()
            statement_value = statement_token.value or ""
            first_definition = len(definitions)

            try:
                if statement_value == "let":
                    self._parse_let_statement(uri, definitions, module_stack)
                elif statement_value == "module":
                    module_name_token = self._parse_module_definition()
                    if module_name_token is not None:
                        pos = module_name_token.start_pos
                        name = module_name_token.get_value(self.text)
                        parent = module_stack[-1] if module_stack else None
                        module = Module(
                            name, parent, pos, uri,
                            module_name_token.get_start_position(self._line_starts),
                        )
                        if parent is not None:
                            parent.modules.append(module)
                        module_stack.append(module)
                        modules.append(module)
                    # `module Module = struct` is not followed by `;;`.
                    continue
                elif statement_value == "end":
                    if module_stack:
                        module = module_stack.pop()
                        module.end = statement_token.end_pos
                        module.end_position = statement_token.get_end_position(self._line_starts)
                    else:
                        self._report("Unexpected end", statement_token, uri)
                    # Some `end` tokens are not followed by `;;`.
                    continue
                elif statement_value in ("open", "include"):
                    name_token = self.expect(TokenType.identifier)
                    module = module_stack[-1] if module_stack else global_module
                    decl = OpenDecl(
                        name_token.get_value(self.text),
                        statement_token.start_pos,
                        name_token.end_pos,
                    )
                    if statement_value == "include":
                        module.include_decls.append(decl)
                    else:
                        module.open_decls.append(decl)
            except ParserError as err:
                self._report(f"Error: {err}", err.token, uri)

            self.reset_state(state)
            # lastIndexOf('\n', startPos - 1): the newline at or before the token.
            line_start = self.text.rfind("\n", 0, statement_token.start_pos) + 1
            column = statement_token.start_pos - line_start
            self.skip_to_next_statement(len(module_stack) > 0, column)
            if len(definitions) > first_definition:
                end = self.pos
                while end > statement_token.start_pos and self.text[end - 1].isspace():
                    end -= 1
                source_range = Range(statement_token.get_start_position(self._line_starts),
                                     end_position(self._line_starts, end))
                for found in definitions[first_definition:]:
                    found.source_start = statement_token.start_pos
                    found.source_end = end
                    found.source_range = source_range

        if module_stack:
            for mod in module_stack:
                self._report(f"Unclosed module: {mod.name}", mod.start, uri)

        return ParseResult(definitions, modules, dependencies, global_module, self._constants)

    def _report(self, message: str, token_or_offset: Token | int | None, uri: str) -> None:
        """Warn about something the parser skipped or misread."""
        if isinstance(token_or_offset, Token):
            offset = token_or_offset.start_pos
        else:
            offset = token_or_offset
        if offset is None:
            line, col = 0, 0
        else:
            upto = self.text[:offset]
            line = len(upto.split("\n"))
            col = offset - (upto.rfind("\n") + 1) + 1
        logger.warning("%s %s:%d:%d", message, uri, line, col)
