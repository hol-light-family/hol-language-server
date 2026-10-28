"""HOL terms: the constants a definition's term introduces."""

import re


def declared_infixes(text: str) -> set[str]:
    """Names the text declares infix with `parse_as_infix("name", ...)`."""
    return set(re.findall(r'parse_as_infix\s*\(\s*"([^"]+)"', text))


# HOL term tokens: names, numbers, brackets, and runs of symbol characters,
# which may end in a name part (`<=_c`). `.` stands alone, so `!x.~p` reads
# as `!`, `x`, `.`, `~`, `p`; `..` is one symbol.
HOL_TOKEN_RE = re.compile(
    r"[A-Za-z_][\w']*|\d\w*|\.\.+|[()\[\]{},;.]|[-\\!@#$%^&*+|<=>/?:~]+(?:_\w+)?"
)
_HOL_OPEN = {"(", "[", "{"}
_HOL_CLOSE = {")", "]", "}"}
_HOL_BINDERS = {"!", "?", "?!", "\\", "@", "lambda"}
# Their body extends as far right as possible: `@y. p /\ q` is one term.
_HOL_OPAQUE = _HOL_BINDERS | {"if", "let", "match", "function"}

type _Tokens = list[tuple[str, int]]


def _is_hol_name(token: str) -> bool:
    return token[:1].isalpha() or token[:1] == "_"


def _hol_tokens(term: str) -> _Tokens:
    return [(m.group(0), m.start()) for m in HOL_TOKEN_RE.finditer(term)]


def _is_hol_symbol(token: str) -> bool:
    return not (_is_hol_name(token) or token[:1].isdigit()
                or token in _HOL_OPEN or token in _HOL_CLOSE or token in (",", ";", ".", "~"))


def _split_top(tokens: _Tokens, separators: set[str]) -> list[_Tokens]:
    """The tokens split at separators outside brackets, up to a binder or
    `if` that does not start its part."""
    parts: list[_Tokens] = [[]]
    depth = 0
    opaque = False
    for tok in tokens:
        if tok[0] in _HOL_CLOSE:
            depth -= 1
        if depth == 0 and not opaque and tok[0] in separators:
            parts.append([])
            continue
        if depth == 0 and tok[0] in _HOL_OPAQUE and parts[-1]:
            opaque = True
        parts[-1].append(tok)
        if tok[0] in _HOL_OPEN:
            depth += 1
    return parts


def _closing(tokens: _Tokens) -> int:
    """Index of the bracket closing tokens[0], else len(tokens)."""
    depth = 0
    for i, tok in enumerate(tokens):
        if tok[0] in _HOL_OPEN:
            depth += 1
        elif tok[0] in _HOL_CLOSE:
            depth -= 1
            if depth == 0:
                return i
    return len(tokens)


def _strip_clause(tokens: _Tokens, bound: set[str]) -> _Tokens:
    """The clause without enclosing brackets and leading `!x y.` binders,
    whose names are added to bound."""
    while tokens:
        if tokens[0][0] == "(" and _closing(tokens) == len(tokens) - 1:
            tokens = tokens[1:-1]
        elif tokens[0][0] == "!":
            dot = next((i for i, t in enumerate(tokens) if t[0] == "."), None)
            if dot is None:
                return []
            bound.update(t[0] for t in tokens[1:dot] if _is_hol_name(t[0]))
            tokens = tokens[dot + 1:]
        else:
            break
    return tokens


def _head(lhs: _Tokens, infixes: set[str], bound: set[str]) -> tuple[str, int] | None:
    """The constant applied on the left side of an equation: `f` in `f x y`,
    `(f:A->B) x`, `(f x) y`, or `x f y` (f a symbol or infix)."""
    atoms: list[_Tokens] = []
    depth = 0
    for tok in lhs:
        if depth == 0 and tok[0] == ":":
            break
        if depth == 0:
            atoms.append([])
        atoms[-1].append(tok)
        if tok[0] in _HOL_OPEN:
            depth += 1
        elif tok[0] in _HOL_CLOSE:
            depth -= 1
    if not atoms or any(a[0][0] == "," for a in atoms[1:]):
        return None
    # A declared infix, also after a typed operand: `f:A->real has_limsup l`.
    depth = 0
    for i, tok in enumerate(lhs):
        if tok[0] in _HOL_OPEN:
            depth += 1
        elif tok[0] in _HOL_CLOSE:
            depth -= 1
        elif depth == 0 and i > 0 and tok[0] in infixes:
            return tok
    symbol = next((a[0] for a in atoms[1:] if len(a) == 1 and _is_hol_symbol(a[0][0])), None)
    if symbol is not None:
        return symbol
    second = atoms[1][0] if len(atoms) >= 2 and len(atoms[1]) == 1 and _is_hol_name(atoms[1][0][0]) else None
    if second is not None and len(atoms) >= 3 and atoms[0][0][0] in bound:
        return second
    first = atoms[0]
    if len(first) == 1:
        tok = first[0][0]
        return first[0] if (_is_hol_name(tok) or _is_hol_symbol(tok)) and tok not in _HOL_BINDERS else None
    if first[0][0] != "(":
        return None
    inner = first[1:_closing(first)]
    if len(inner) == 1:
        # An operator or binder in brackets: `(/\) = ...`, `(!) = ...`.
        return inner[0]
    # `(f:num->num) x`, `(f x) y`.
    found = _head(inner, infixes, bound)
    if found is None and second is not None and len(atoms) >= 3:
        # `(x1,y1) f (x2,y2)`: an infix after a tuple.
        return second
    return found


def term_constants(term: str, infixes: set[str], inductive: bool) -> list[tuple[str, int]]:
    """Constants a definition's term introduces, with their offsets in the
    term: the head of the left side of each `/\\` clause, as in
    `fib 0 = 0 /\\ fib (n + 1) = ...`, or of each rule's conclusion for an
    inductive definition. An infix head (`x IN s`, `m <= n`) is found when it
    is a symbol, is in infixes, or the name before it is bound by `!`."""
    tokens = _hol_tokens(term)
    # `<=>` binds looser than `/\`: a term with `<=>` outside brackets is one equation.
    if inductive or len(_split_top(tokens, {"<=>"})) == 1:
        clauses = _split_top(tokens, {"/\\"})
    else:
        clauses = [tokens]
    found: list[tuple[str, int]] = []
    for clause in clauses:
        bound: set[str] = set()
        clause = _strip_clause(clause, bound)
        sides = _split_top(clause, {"<=>"})
        if len(sides) == 1:
            # Hypotheses of a conditional equation or a rule: `p ==> f x = y`.
            sides = _split_top(_strip_clause(_split_top(clause, {"==>"})[-1], bound), {"="})
            if len(sides) == 1 and not inductive:
                continue
        head = _head(sides[0], infixes, bound)
        if head is not None and head[0] not in bound and all(head[0] != f[0] for f in found):
            found.append(head)
    return found
