# -*- coding: utf-8 -*-
"""导出 FastAPI openapi.json，供前端 openapi-typescript 生成 TS 类型。

用法: python scripts/gen_openapi.py
输出: web/src/api/openapi.json（前端 npm run gen:api 的中间产物，已 gitignore）
"""
import json
import sys
from pathlib import Path

# CI(GitHub Actions) 的 Windows Python stdout 为 cp1252，打印 → 等 Unicode 会抛
# UnicodeEncodeError → 强制 UTF-8 输出
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402  （触发 FastAPI 路由注册）

out = ROOT / "web" / "src" / "api" / "openapi.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(server.app.openapi(), ensure_ascii=False), encoding="utf-8")
print(f"openapi.json → {out}")
