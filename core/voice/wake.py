# -*- coding: utf-8 -*-
"""桌面语音监听 — 本地唤醒词常驻麦克风 + 停止命令词即时截获

命令词（停止/取消/暂停/够了）不经 LLM，直接返回 True 供外部触发 StopController。
实时监听基于 vosk + sounddevice；缺依赖/模型/麦克风时 start() 返回 False（优雅降级）。
"""
import json
import os
import threading

from core.config import ROOT_DIR, cfg
from core.logger import logger

_STOP_WORDS = ("停止", "取消", "暂停", "够了", "停下", "别做了")


def is_stop_command(text: str) -> bool:
    """命中停止命令词返回 True（用于即时截获，不走 LLM）。"""
    t = (text or "").strip()
    return any(w in t for w in _STOP_WORDS)


class WakeListener:
    """桌面常驻唤醒词监听：唤醒词 → 录音(≤max_ms/静音停) → on_utterance(text)。

    依赖 vosk + sounddevice；available() 为 False 或模型缺失时 start() 返回 False。
    """

    SAMPLE_RATE = 16000
    BLOCK = 8000  # 采样块（~0.5s）

    def __init__(self, keyword: str | None = None, model_path: str | None = None):
        self.keyword = keyword or cfg("voice.wake_word.keyword", "小逻小逻")
        # 桌面监听优先本地模型目录（local_model），否则回退浏览器端 URL
        local = cfg("voice.wake_word.local_model", "")
        self.model_path = model_path or local or cfg("voice.wake_word.model_path", "")
        if self.model_path and not os.path.isabs(self.model_path):
            self.model_path = str(ROOT_DIR / self.model_path)
        self._running = False
        self._thread: threading.Thread | None = None
        self._on_utterance = None

    def available(self) -> bool:
        try:
            import vosk  # noqa: F401
            import sounddevice  # noqa: F401
            return True
        except ImportError:
            return False

    def start(self, on_utterance) -> bool:
        """on_utterance: async (text: str) -> None。返回是否成功启动。"""
        if not self.available():
            logger.warning("vosk/sounddevice 未安装，桌面语音监听不可用")
            return False
        if not self.model_path:
            logger.warning("未配置 vosk 模型路径（voice.wake_word.model_path），桌面语音监听不可用")
            return False
        import os
        if not os.path.isdir(self.model_path) and not os.path.isfile(self.model_path):
            logger.warning("vosk 模型路径不存在（{}），桌面语音监听不可用", self.model_path)
            return False
        self._on_utterance = on_utterance
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        self._thread = None

    def _dispatch(self, text: str) -> None:
        if not text or not self._on_utterance:
            return
        try:
            import asyncio
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._on_utterance(text))
            else:
                asyncio.ensure_future(self._on_utterance(text))
        except Exception as e:
            logger.warning("on_utterance 调用失败: {}", e)

    def _run(self) -> None:
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
            SetLogLevel(-1)
            import sounddevice as sd
        except ImportError:
            logger.warning("vosk/sounddevice 缺失，监听退出")
            return
        try:
            model = Model(self.model_path)
        except Exception as e:
            logger.warning("vosk 模型加载失败（{}）。模型需为解压目录，可复用 web/public/models 下的模型。", e)
            return
        logger.info("WakeListener 监听中：说「{}」唤醒（model={}）", self.keyword, self.model_path)
        try:
            with sd.RawInputStream(samplerate=self.SAMPLE_RATE, blocksize=self.BLOCK,
                                   dtype="int16", channels=1) as stream:
                # 阶段一：关键词识别（只等唤醒词）
                rec = KaldiRecognizer(model, self.SAMPLE_RATE, json.dumps([self.keyword]))
                while self._running:
                    data, _ = stream.read(self.BLOCK)
                    if rec.AcceptWaveform(data):
                        logger.info("已唤醒「{}」，开始识别指令", self.keyword)
                        break
                # 阶段二：指令识别（正常识别，最长 10s）
                rec2 = KaldiRecognizer(model, self.SAMPLE_RATE)
                rec2.SetWords(False)
                text_buf = []
                for _ in range(20):  # 10s 上限
                    if not self._running:
                        break
                    data, _ = stream.read(self.BLOCK)
                    if rec2.AcceptWaveform(data):
                        text_buf.append(json.loads(rec2.Result()).get("text", ""))
                final = "".join(text_buf).strip()
                self._dispatch(final)
        except Exception as e:
            logger.warning("WakeListener 退出: {}", e)
