# -*- coding: utf-8 -*-
"""协议间共享的辅助函数。Helpers shared across protocol adapters."""
import httpx


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """从消息中拆出 system 内容（合并为一段），返回 (system, 其余消息)。Extract the system content from messages (joined into one string), returning (system, remaining messages)."""
    system_parts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
    return "\n\n".join(system_parts), [m for m in messages if m.get("role") != "system"]


async def _raise_for_status_read(resp: httpx.Response) -> None:
    """raise_for_status，但非 2xx 时先读实体再放异常出去。

    在 client.stream() 上下文内裸调 raise_for_status，抛出的 HTTPStatusError
    携带的是**未读**的流式响应 —— 下游读 .text 会抛 ResponseNotRead
    （“Attempted to access streaming response content…”），把上游 400/404 的
    真实正文顶掉：failover 启发式失效、日志无痕（截图 bug #2）。先 aread()
    标记实体已读，.text 在上下文退出后照常可取。

    raise_for_status, but read the entity first on non-2xx so the exception
    leaves with its body readable. A bare raise_for_status inside the
    client.stream() context carries an UNREAD streaming response — a downstream
    .text read throws ResponseNotRead (“Attempted to access streaming response
    content…”) and masks the upstream 400/404 body: the failover heuristic dies
    and nothing reaches the log (screenshot bug #2). aread() marks the entity
    read, so .text stays usable after the context exits.

    Args:
        resp: 流式响应。The streaming response.

    Raises:
        httpx.HTTPStatusError: 非 2xx（实体已读）。Non-2xx (entity already read).
    """
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError:
        await resp.aread()
        raise
