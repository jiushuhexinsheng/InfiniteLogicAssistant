# -*- coding: utf-8 -*-
"""停止/中止控制器 — CancellationToken 贯穿执行层与子进程

stop_task(整个任务)：cancel 同一 token，执行层每个工具调用与子进程（run_shell）都检查并中止。

Stop/abort controller — a CancellationToken threaded through the execution layer
and child processes. stop_task (the whole task) cancels the same token; every
tool call and child process (run_shell) in the execution layer checks it and aborts.
"""
import asyncio
import enum


class CancellationToken:
    """取消令牌：cancel() 置位取消标志，执行点检查 is_cancelled / throw_if_cancelled 中止。

    Cancellation token: cancel() sets the cancellation flag; execution points
    check is_cancelled / throw_if_cancelled to abort.
    """

    def __init__(self) -> None:
        """初始化取消令牌（初始为未取消状态）。

        Initialize the cancellation token (initially not cancelled).
        """
        self._cancelled = False

    def cancel(self) -> None:
        """请求取消（置位取消标志）。Request cancellation (set the cancellation flag)."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """是否已请求取消。Whether cancellation has been requested."""
        return self._cancelled

    def throw_if_cancelled(self) -> None:
        """已取消时抛出 asyncio.CancelledError，供执行点协作式中止。

        Raise asyncio.CancelledError when cancelled, enabling cooperative
        cancellation at execution points.
        """
        if self._cancelled:
            raise asyncio.CancelledError


class StopController:
    """停止控制器：持有唯一 token，stop_task() 取消整个任务（含子进程）。

    Stop controller: holds the single token; stop_task() cancels the whole task,
    including child processes.
    """

    def __init__(self) -> None:
        """初始化控制器并创建取消令牌。Initialize the controller and create the cancellation token."""
        self.token = CancellationToken()

    def stop_task(self) -> None:
        """停止整个任务（含子进程，由各执行点检查 token 并 kill）。

        Stop the entire task (including child processes; each execution point
        checks the token and kills as needed).
        """
        self.token.cancel()


class PauseMode(str, enum.Enum):
    """暂停的三种语义（参照 DSH task-control）。

    Pause semantics (mirroring DSH task-control):
    - SAFE_WAIT: 当前 LLM/工具自然完成，到步骤边界才真正停住；
    - SAFE_STOP: 立即中断 LLM 生成（保留已生成部分），等当前工具结束后停住；
    - FORCE: 立即中断 LLM 与在途工具。
    """

    SAFE_WAIT = "wait"
    SAFE_STOP = "stop"
    FORCE = "force"


class PauseController:
    """暂停控制器：与 CancellationToken 并列，不取消任务，只挂起。

    恢复后从步骤边界继续；被 force 中断的工具记录在 `interrupted_tools`，恢复时
    由上层决定重跑或跳过。

    Pause controller: sits beside CancellationToken; suspends rather than cancels.
    After resume the loop continues at the step boundary; tools interrupted by FORCE
    are recorded in `interrupted_tools` for a rerun/skip decision.
    """

    def __init__(self) -> None:
        """初始化：默认未暂停、safe wait。"""
        self.mode: PauseMode = PauseMode.SAFE_WAIT
        self._paused = False
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._force_event = asyncio.Event()
        self.interrupted_tools: list[dict] = []

    @property
    def paused(self) -> bool:
        """是否处于暂停。Whether paused."""
        return self._paused

    def pause(self, mode: PauseMode = PauseMode.SAFE_WAIT) -> None:
        """请求暂停（同一时刻只保留最后一次模式）。Request a pause."""
        self.mode = mode
        self._paused = True
        self._resume_event.clear()
        if mode == PauseMode.FORCE:
            self._force_event.set()
        else:
            self._force_event.clear()

    def resume(self) -> None:
        """恢复运行（不清理中断记录）。Resume (interrupted record is kept)."""
        self._paused = False
        self._resume_event.set()
        self._force_event.clear()

    async def wait_if_paused(self) -> None:
        """暂停期间阻塞；恢复后立即返回。Block while paused."""
        if self._paused:
            await self._resume_event.wait()

    async def wait_force(self) -> None:
        """等待 force 暂停发生（工具执行竞速用）。Wait until FORCE pause is requested."""
        await self._force_event.wait()

    @property
    def abort_llm(self) -> bool:
        """当前暂停模式是否应立即中断 LLM。Whether LLM generation should abort."""
        return self._paused and self.mode in (PauseMode.SAFE_STOP, PauseMode.FORCE)

    @property
    def abort_tools(self) -> bool:
        """当前暂停模式是否应立即中断在途工具。Whether in-flight tools should abort."""
        return self._paused and self.mode == PauseMode.FORCE

    def record_interrupted(self, tool: str, args: dict, risk: str) -> None:
        """记录被暂停中断的工具。Record a tool interrupted by pause."""
        self.interrupted_tools.append({"tool": tool, "args": dict(args), "risk": risk})

    def clear_interrupted(self) -> None:
        """清空中断记录（恢复流程处理完后调用）。Clear the interrupted list."""
        self.interrupted_tools.clear()
