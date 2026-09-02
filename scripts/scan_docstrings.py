"""扫描项目所有 py 文件的 docstring 覆盖情况，输出报告。

Scan all project .py files for docstring coverage and print a report.
"""
import ast
import pathlib

root = pathlib.Path(r"D:\编程项目\AI\InfiniteLogicAssistant")
skip = {"__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".git", "node_modules"}
files = sorted(f for f in root.rglob("*.py") if not any(s in f.parts for s in skip))

total_files = 0
files_with_issues = 0
missing_docstrings = []

for f in files:
    rel = f.relative_to(root)
    try:
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception:
        print(f"  PARSE_ERROR: {rel}")
        continue

    total_files += 1

    # 模块级 docstring
    mod_ds = bool(ast.get_docstring(tree))

    missing = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not ast.get_docstring(node):
                missing.append(f"  func {node.name} (L{node.lineno})")
        elif isinstance(node, ast.ClassDef):
            if not ast.get_docstring(node):
                missing.append(f"  class {node.name} (L{node.lineno})")

    if not mod_ds:
        missing.insert(0, f"  [模块 docstring 缺失]")

    if missing:
        files_with_issues += 1
        print(f"\n{rel}  ({len(missing)} 处缺失)")
        for m in missing:
            print(m)
            missing_docstrings.append(f"{rel}::{m}")

print(f"\n{'='*60}")
print(f"扫描完成: {total_files} 个文件, {files_with_issues} 个文件缺注释, {len(missing_docstrings)} 处待补充")
