# -*- coding: utf-8 -*-
"""任务库下线（docs/designs/10 6.1）。

TaskStore 没有运行时写入方，任务库永远是空的；端点保留一个版本供旧前端调用：
列表返回空，详情/删除返回 410（Gone）。

The task library is offline (docs/designs/10 6.1): TaskStore has no runtime writer,
so the library can only ever be empty. The endpoints stay for one release for old
frontends: the list returns empty, detail/delete return 410 Gone.
"""


def test_library_list_is_empty(client):
    """列表恒为空（不再读 TaskStore）。The list is always empty (TaskStore is not read)."""
    r = client.get("/api/library")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["tasks"] == []


def test_library_detail_and_delete_gone(client):
    """详情与删除标记下线（410），不再操作存档。Detail and delete are gone (410)."""
    assert client.get("/api/library/1").status_code == 410
    assert client.delete("/api/library/1").status_code == 410
