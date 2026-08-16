# -*- coding: utf-8 -*-
"""memory / env 域 API — 环境快照 / 长期记忆浏览与删除"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/env")
async def env():
    from core.execution.envprobe import read_environment_md
    return {"ok": True, "content": await read_environment_md()}


@router.get("/memory")
async def memory_list():
    from core.memory.context import get_facts_store
    return {"ok": True, "facts": await get_facts_store().all()}


@router.delete("/memory/{topic}")
async def memory_delete(topic: str):
    from core.memory.context import get_facts_store
    await get_facts_store().delete(topic)
    return {"ok": True}
