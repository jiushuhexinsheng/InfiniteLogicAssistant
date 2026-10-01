# -*- coding: utf-8 -*-
"""协议间共享的辅助函数。Helpers shared across protocol adapters."""
def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """从消息中拆出 system 内容（合并为一段），返回 (system, 其余消息)。Extract the system content from messages (joined into one string), returning (system, remaining messages)."""
    system_parts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
    return "\n\n".join(system_parts), [m for m in messages if m.get("role") != "system"]
