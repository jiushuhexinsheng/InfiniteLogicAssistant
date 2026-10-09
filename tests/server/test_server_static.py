# -*- coding: utf-8 -*-
"""静态托管 / SPA 兜底 / 路径穿越。Static file hosting, SPA fallback and path traversal."""
import server as server_module


# ─── 静态托管 / SPA 兜底 / 路径穿越 ───

def test_static_index(client):
    """测试静态首页托管。Tests static index page hosting."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.text == "<html>spa</html>"


def test_static_file_and_spa_fallback(client):
    """测试静态文件托管与 SPA 兜底。Tests static file hosting and the SPA fallback."""
    dist = server_module.WEB_DIST_DIR
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("JS", encoding="utf-8")
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/app.js").text == "JS"
    # 不存在的非 api 路径 → SPA 兜底 index.html
    resp = client.get("/some/route")
    assert resp.status_code == 200
    assert resp.text == "<html>spa</html>"


def test_unknown_api_404(client):
    """测试未知 API 路径返回 404。Tests unknown API paths returning 404."""
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.json()["ok"] is False


def test_resolve_dist_rejects_traversal(client):
    """测试 _resolve_dist 拒绝路径穿越。Tests _resolve_dist rejecting path traversal."""
    # 直接测 _resolve_dist：httpx/TestClient 会归一化 URL 里的 ../，HTTP 层测不到原始路径
    assert server_module._resolve_dist("../config.yaml") is None
    assert server_module._resolve_dist("..\\config.yaml") is None
    # 前导 / 会被剥掉按 dist 内相对路径解析，绝不会越出 dist
    p = server_module._resolve_dist("/etc/passwd")
    assert p is not None
    assert str(p).startswith(str(server_module.WEB_DIST_DIR.resolve()))
    assert server_module._resolve_dist("assets/app.js").name == "app.js"
