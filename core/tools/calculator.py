# -*- coding: utf-8 -*-
"""安全算术计算器 — ast 白名单求值，禁 exec/eval

Safe arithmetic calculator — evaluates via an AST whitelist; exec/eval are forbidden.
"""
import ast
import operator
from typing import Any, Callable

from core.tools.base import tool

_OPS: dict[type, Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST):
    """用白名单递归求值 AST 节点，仅允许数值常量与算术运算。

    Recursively evaluate an AST node with a whitelist, allowing only numeric constants and arithmetic operations.

    Args:
        node: AST 节点。AST node.

    Returns:
        求值结果。Evaluation result.

    Raises:
        ValueError: 表达式包含白名单外的节点时。When the expression contains a node outside the whitelist.
    """
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("不支持的表达式")


@tool("安全计算数学表达式（如 '2+3*4'）")
def calculate(expression: str) -> str:
    """安全计算数学表达式（如 "2+3*4"），出错返回 "Error: ..."。

    Safely evaluate a math expression (e.g. "2+3*4"); returns "Error: ..." on failure.

    Args:
        expression: 数学表达式。Math expression.

    Returns:
        计算结果或错误信息。Computed result or error message.
    """
    try:
        return str(_safe_eval(ast.parse(expression, mode="eval")))
    except Exception as exc:
        return f"Error: {exc}"
