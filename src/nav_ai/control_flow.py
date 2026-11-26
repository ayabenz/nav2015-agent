"""Conservative C/AL control-flow extraction.

This is a source-structure analyzer, not a compiler or runtime evaluator. It
preserves raw predicates and source spans; unsupported statements remain opaque.
"""
from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(
    r"""(?P<WS>\s+)|(?P<LINE>//[^\r\n]*)|(?P<BLOCK>\{(?:[^{}]|\{[^{}]*\})*\})|"""
    r"""(?P<SQ>'(?:''|[^'])*')|(?P<DQ>"(?:""|[^"])*")|"""
    r"""(?P<OP><=|>=|<>|:=|::|\.\.|[=<>+\-*/])|"""
    r"""(?P<WORD>[A-Za-z_][A-Za-z0-9_@]*)|(?P<NUM>\d+(?:\.\d+)?)|(?P<PUNC>[()[\].,:;])|(?P<OTHER>.)""",
    re.S,
)
_KEYWORDS = {"IF", "THEN", "ELSE", "CASE", "OF", "BEGIN", "END"}


def tokenize(source: str) -> list[dict[str, Any]]:
    """Tokenize C/AL while ignoring comments and retaining absolute offsets."""
    out = []
    for m in _TOKEN.finditer(source):
        kind = m.lastgroup
        if kind in {"WS", "LINE", "BLOCK"}:
            continue
        value = m.group()
        out.append({
            "value": value,
            "upper": value.upper() if kind == "WORD" else value,
            "kind": kind,
            "start": m.start(),
            "end": m.end(),
            "line": source.count("\n", 0, m.start()) + 1,
        })
    return out


class _Parser:
    def __init__(self, source: str):
        self.source = source
        self.tokens = tokenize(source)
        self.i = 0
        self.diagnostics: list[str] = []

    def peek(self, value: str | None = None) -> bool:
        if self.i >= len(self.tokens):
            return False
        return value is None or self.tokens[self.i]["upper"] == value

    def take(self) -> dict[str, Any]:
        token = self.tokens[self.i]
        self.i += 1
        return token

    def span(self, start: int, end: int) -> dict[str, int]:
        if start >= end:
            pos = self.tokens[start - 1]["end"] if start else 0
            return {"start": pos, "end": pos, "line_start": self.source.count("\n", 0, pos) + 1,
                    "line_end": self.source.count("\n", 0, pos) + 1}
        a, b = self.tokens[start], self.tokens[end - 1]
        return {"start": a["start"], "end": b["end"], "line_start": a["line"],
                "line_end": b["line"]}

    def expression_until(self, stop: set[str]) -> tuple[str, int, int]:
        start = self.i
        depth = 0
        while self.i < len(self.tokens):
            t = self.tokens[self.i]["upper"]
            if depth == 0 and t in stop:
                break
            if t in {"(", "["}:
                depth += 1
            elif t in {")", "]"}:
                depth = max(0, depth - 1)
            self.i += 1
        if self.i == start:
            return "", start, self.i
        raw = self.source[self.tokens[start]["start"]:self.tokens[self.i - 1]["end"]].strip()
        return raw, start, self.i

    def parse_statement(self) -> dict[str, Any] | None:
        if self.i >= len(self.tokens):
            return None
        if self.peek("BEGIN"):
            return self.parse_block()
        if self.peek("IF"):
            return self.parse_if()
        if self.peek("CASE"):
            return self.parse_case()
        return self.parse_opaque()

    def parse_block(self) -> dict[str, Any]:
        start = self.i
        self.take()  # BEGIN
        children = []
        while self.i < len(self.tokens) and not self.peek("END"):
            before = self.i
            child = self.parse_statement()
            if child:
                children.append(child)
            if self.i == before:
                self.i += 1
        if self.peek("END"):
            self.take()
            if self.peek(";"):
                self.take()
        else:
            self.diagnostics.append(f"Unclosed BEGIN at line {self.tokens[start]['line']}")
        node = {"type": "block", "children": children}
        node.update(self.span(start, self.i))
        return node

    def parse_if(self) -> dict[str, Any]:
        start = self.i
        self.take()  # IF
        condition, cond_start, cond_end = self.expression_until({"THEN"})
        if not self.peek("THEN"):
            self.diagnostics.append(f"IF without THEN at line {self.tokens[start]['line']}")
            return {"type": "unresolved", "expression": condition, **self.span(start, self.i)}
        self.take()
        true_branch = self.parse_statement()
        false_branch = None
        if self.peek("ELSE"):
            self.take()
            false_branch = self.parse_statement()
        node = {
            "type": "if",
            "condition": condition,
            "condition_span": self.span(cond_start, cond_end),
            "true_branch": true_branch,
            "false_branch": false_branch,
        }
        node.update(self.span(start, self.i))
        return node

    def parse_case(self) -> dict[str, Any]:
        start = self.i
        self.take()  # CASE
        expression, expr_start, expr_end = self.expression_until({"OF"})
        if not self.peek("OF"):
            self.diagnostics.append(f"CASE without OF at line {self.tokens[start]['line']}")
            return {"type": "unresolved", "expression": expression, **self.span(start, self.i)}
        self.take()
        arms = []
        default = None
        while self.i < len(self.tokens) and not self.peek("END"):
            if self.peek("ELSE"):
                self.take()
                default = self.parse_statement()
                continue
            labels, label_start, label_end = self.expression_until({":" , "END", "ELSE"})
            if not self.peek(":"):
                if labels:
                    self.diagnostics.append(f"CASE arm without ':' near line {self.tokens[label_start]['line']}")
                break
            self.take()
            body = self.parse_statement()
            arms.append({"labels": labels, "label_span": self.span(label_start, label_end), "body": body})
            if self.peek(";"):
                self.take()
            elif not self.peek("END"):
                # Recovery: consume one token rather than looping forever.
                self.diagnostics.append(f"Unexpected CASE token at line {self.tokens[self.i]['line']}")
                self.i += 1
        if self.peek("END"):
            self.take()
            if self.peek(";"):
                self.take()
        else:
            self.diagnostics.append(f"Unclosed CASE at line {self.tokens[start]['line']}")
        node = {"type": "case", "expression": expression, "expression_span": self.span(expr_start, expr_end),
                "arms": arms, "default": default}
        node.update(self.span(start, self.i))
        return node

    def parse_opaque(self) -> dict[str, Any]:
        start = self.i
        depth = 0
        while self.i < len(self.tokens):
            value = self.tokens[self.i]["upper"]
            if depth == 0 and value in {"ELSE", "END"}:
                break
            if value in {"(", "["}:
                depth += 1
            elif value in {")", "]"}:
                depth = max(0, depth - 1)
            token = self.take()
            if depth == 0 and token["value"] == ";":
                break
        raw = self.source[self.tokens[start]["start"]:self.tokens[self.i - 1]["end"]].strip()
        node = {"type": "statement", "source": raw}
        node.update(self.span(start, self.i))
        return node


def analyze_control_flow(source: str, object_type: str | None = None, object_id: int | None = None,
                         object_name: str | None = None, procedure: str | None = None,
                         source_file: str = "<memory>") -> dict[str, Any]:
    """Extract IF/ELSE and CASE structure from a procedure or C/AL code region."""
    parser = _Parser(source)
    nodes = []
    while parser.i < len(parser.tokens):
        before = parser.i
        node = parser.parse_statement()
        if node:
            nodes.append(node)
        if parser.i == before:
            parser.i += 1
    return {
        "object": {"type": object_type, "id": object_id, "name": object_name},
        "procedure": procedure,
        "source_file": source_file,
        "analysis": "static_source_structure",
        "runtime_evaluated": False,
        "nodes": nodes,
        "diagnostics": parser.diagnostics,
    }
