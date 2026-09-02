# -*- coding: utf-8 -*-
"""memory / env 域 API — 环境快照 / 长期记忆浏览与删除。

Memory / env domain API — environment snapshot, long-term memory browsing and deletion.
"""
from fastapi import APIRouter

from core.api.schemas import ApiResponse, EnvResponse, MemoryListResponse

router = APIRouter()


@router.get("/env", response_model=EnvResponse)
async def env():
    """读取当前环境快照（environment.md 的内容）。

    Read the current environment snapshot (the content of environment.md).
    """
    from core.detection.environment import read_environment_md
    return {"ok": True, "content": await read_environment_md()}


@router.get("/memory", response_model=MemoryListResponse)
async def memory_list():
    """列出全部长期记忆事实（facts）。

    List all long-term memory facts.
    """
    from core.memory.context import get_facts_store
    return {"ok": True, "facts": await get_facts_store().all()}


@router.delete("/memory/{topic}", response_model=ApiResponse)
async def memory_delete(topic: str):
    """按主题删除一条长期记忆。

    Delete a long-term memory entry by topic.
    """
    from core.memory.context import get_facts_store
    await get_facts_store().delete(topic)
    return {"ok": True}
