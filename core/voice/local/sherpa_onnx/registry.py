# -*- coding: utf-8 -*-
"""模型注册表：扫描 ``models/{vad,kws,asr,tts,llm}``、校验文件、推断家族。

Model registry: scan ``models/{vad,kws,asr,tts,llm}``, validate files, infer family.

设计目标是「只要是兼容的 sherpa-onnx 模型就能用」：不维护模型白名单，而是按
目录里的文件特征识别家族与是否支持流式，再交给对应引擎加载。校验只做文件系统
判断，**不 import sherpa_onnx、更不加载模型**（设置页渲染一个勾选不能付出 500MB
内存的代价）。

The goal is "any compatible sherpa-onnx model works": no allow-list; the family and
streaming capability are inferred from the files present and handed to the matching
engine. Validation is filesystem-only — it must not import sherpa_onnx or load a
model just to render a checkbox in the settings page.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core import config

# 模型能力目录名。Capability directory names.
KINDS = ("vad", "kws", "asr", "tts", "llm")

# ``model.json`` 是可选的；没有时按文件名/目录名推断。
# ``model.json`` is optional; without it, family and streaming are inferred.
MANIFEST_NAME = "model.json"


@dataclass(frozen=True)
class ModelInfo:
    """一个已安装模型的只读描述。Read-only description of one installed model."""

    kind: str
    id: str
    name: str
    path: str                  # 相对项目根的 POSIX 路径（配置里就用它）
    family: str
    streaming: bool
    valid: bool
    missing: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    size_bytes: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转为 JSON 友好的字典。JSON-friendly dict."""
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "family": self.family,
            "streaming": self.streaming,
            "valid": self.valid,
            "missing": list(self.missing),
            "files": list(self.files),
            "size_bytes": self.size_bytes,
            "metadata": dict(self.metadata),
        }


def models_root() -> Path:
    """模型根目录（``<项目>/models``）。Model root (``<project>/models``)."""
    return Path(config.ROOT_DIR) / "models"


def kind_root(kind: str) -> Path:
    """某能力的模型目录。The model directory for one capability."""
    if kind not in KINDS:
        raise ValueError(f"未知模型类型: {kind!r}（可选 {', '.join(KINDS)}）")
    return models_root() / kind


def _rel(path: Path) -> str:
    """路径 → 相对项目根的 POSIX 字符串（不在根下则原样）。Path → root-relative POSIX."""
    root = Path(config.ROOT_DIR).resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return str(path)


def _nonempty(path: Path) -> bool:
    """文件存在且非空。File exists and is non-empty."""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _glob(d: Path, *patterns: str) -> list[Path]:
    """按多个 glob 收集非空文件（去重排序）。Collect non-empty files for patterns."""
    out: dict[str, Path] = {}
    for pat in patterns:
        for p in d.glob(pat):
            if _nonempty(p):
                out[str(p)] = p
    return [out[k] for k in sorted(out)]


def _load_manifest(d: Path) -> dict[str, Any]:
    """读取可选的 ``model.json``；损坏时忽略（不因元数据坏了而判模型不可用）。

    Read the optional ``model.json``; a broken manifest is ignored (a bad manifest
    must not invalidate an otherwise usable model).
    """
    mf = d / MANIFEST_NAME
    if not mf.is_file():
        return {}
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _family_from_name(name: str, fallback: str) -> str:
    """按目录/文件名推断家族。Infer family from the directory/file name."""
    low = name.lower()
    if "sense-voice" in low or "sensevoice" in low:
        return "sense-voice"
    if "paraformer" in low:
        return "paraformer"
    if "whisper" in low:
        return "whisper"
    if "moonshine" in low:
        return "moonshine"
    if "nemo" in low:
        return "nemo"
    if "zipformer" in low and "ctc" in low:
        return "zipformer-ctc"
    if "ctc" in low:
        return "ctc"
    if "kokoro" in low:
        return "kokoro"
    if "vits" in low:
        return "vits"
    if "matcha" in low:
        return "matcha"
    if "ten" in low and "vad" in low:
        return "ten-vad"
    if "silero" in low:
        return "silero"
    return fallback


def _inspect_vad(path: Path) -> ModelInfo:
    """VAD 模型：单文件 ONNX。VAD model: a single ONNX file."""
    files = (path.name,) if _nonempty(path) else ()
    family = _family_from_name(path.name, "unknown")
    if family not in ("ten-vad", "silero"):
        family = "ten-vad" if "ten" in path.name.lower() else "silero"
    return ModelInfo(
        kind="vad", id=path.stem, name=path.stem, path=_rel(path),
        family=family, streaming=False, valid=bool(files),
        missing=() if files else (path.name,),
        files=files, size_bytes=path.stat().st_size if path.is_file() else 0,
        metadata=_load_manifest(path.parent) if path.parent.name == "vad" else {},
    )


def _asr_layout(d: Path) -> tuple[str, bool, tuple[str, ...], tuple[str, ...]]:
    """推断 ASR 家族 / 流式 / 已存在文件 / 缺失文件。

    Infer ASR family, streaming capability, present files and missing files.
    """
    tokens = _glob(d, "tokens.txt")
    enc = _glob(d, "encoder*.onnx")
    dec = _glob(d, "decoder*.onnx")
    joiner = _glob(d, "joiner*.onnx")
    model = _glob(d, "model*.onnx")
    manifest = _load_manifest(d)
    name = d.name.lower()

    family = str(manifest.get("family") or "")
    if not family:
        if enc and dec and joiner:
            family = "transducer"
        elif enc and dec and "paraformer" in name:
            # 在线 paraformer 用 encoder/decoder，没有 joiner。
            # Online paraformer ships encoder/decoder and no joiner.
            family = "paraformer"
        elif "sense-voice" in name or "sensevoice" in name:
            family = "sense-voice"
        elif "paraformer" in name:
            family = "paraformer"
        elif "whisper" in name:
            family = "whisper"
        elif "wenet" in name:
            family = "wenet"
        elif "nemo" in name:
            family = "nemo"
        elif "t-one" in name or "t_one" in name:
            family = "t-one"
        elif model:
            family = _family_from_name(d.name, "offline")
        else:
            family = "unknown"

    streaming = manifest.get("streaming")
    if streaming is None:
        streaming = "streaming" in name or family in ("transducer", "wenet", "nemo", "t-one")
        # 在线 paraformer 的名字里通常也带 streaming；没有时按「有 encoder+decoder
        # 且没有 joiner」推断。Online paraformer usually says streaming; infer from
        # encoder+decoder without joiner otherwise.
        if family == "paraformer":
            streaming = "streaming" in name or (bool(enc and dec) and not joiner)
    streaming = bool(streaming)

    present = [p.name for p in tokens + enc + dec + joiner + model]
    missing: list[str] = []
    if not tokens:
        missing.append("tokens.txt")
    if family == "transducer":
        if not enc:
            missing.append("encoder*.onnx")
        if not dec:
            missing.append("decoder*.onnx")
        if not joiner:
            missing.append("joiner*.onnx")
    elif family == "paraformer":
        if streaming:
            if not enc:
                missing.append("encoder*.onnx")
            if not dec:
                missing.append("decoder*.onnx")
        elif not model:
            missing.append("model*.onnx")
    elif family == "whisper":
        if not enc:
            missing.append("encoder*.onnx")
        if not dec:
            missing.append("decoder*.onnx")
    elif family in ("sense-voice", "offline", "ctc", "zipformer-ctc", "nemo", "wenet", "t-one"):
        if not model:
            missing.append("model*.onnx")
    else:
        if not (model or (enc and dec)):
            missing.append("model*.onnx 或 encoder/decoder")

    return family, streaming, tuple(present), tuple(missing)


def _inspect_asr(d: Path) -> ModelInfo:
    """ASR 模型目录。ASR model directory."""
    family, streaming, present, missing = _asr_layout(d)
    return ModelInfo(
        kind="asr", id=d.name, name=d.name, path=_rel(d),
        family=family, streaming=streaming, valid=not missing,
        missing=missing, files=present,
        size_bytes=_dir_size(d), metadata=_load_manifest(d),
    )


def _inspect_kws(d: Path) -> ModelInfo:
    """KWS 模型目录：tokens + encoder/decoder/joiner。KWS model directory."""
    tokens = _glob(d, "tokens.txt")
    enc = _glob(d, "encoder*.onnx")
    dec = _glob(d, "decoder*.onnx")
    joiner = _glob(d, "joiner*.onnx")
    missing: list[str] = []
    if not tokens:
        missing.append("tokens.txt")
    if not enc:
        missing.append("encoder*.onnx")
    if not dec:
        missing.append("decoder*.onnx")
    if not joiner:
        missing.append("joiner*.onnx")
    present = tuple(p.name for p in tokens + enc + dec + joiner)
    return ModelInfo(
        kind="kws", id=d.name, name=d.name, path=_rel(d),
        family="zipformer-kws", streaming=True, valid=not missing,
        missing=tuple(missing), files=present,
        size_bytes=_dir_size(d), metadata=_load_manifest(d),
    )


def _tts_layout(d: Path) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """推断 TTS 家族 / 已存在文件 / 缺失文件。Infer TTS family and files."""
    model = _glob(d, "model*.onnx")
    tokens = _glob(d, "tokens.txt")
    voices = _glob(d, "voices.bin", "voices.txt")
    data_dir = d / "espeak-ng-data"
    manifest = _load_manifest(d)

    family = str(manifest.get("family") or "")
    if not family:
        if voices:
            family = "kokoro"
        elif _glob(d, "acoustic_model*.onnx") and _glob(d, "vocoder*.onnx"):
            family = "matcha"
        else:
            family = _family_from_name(d.name, "vits")

    missing: list[str] = []
    if not model:
        missing.append("model*.onnx")
    if not tokens:
        missing.append("tokens.txt")
    if family == "kokoro":
        if not voices:
            missing.append("voices.bin")
        if not data_dir.is_dir():
            missing.append("espeak-ng-data/")

    present = [p.name for p in model + tokens + voices]
    if data_dir.is_dir():
        present.append("espeak-ng-data/")
    return family, tuple(present), tuple(missing)


def _inspect_tts(d: Path) -> ModelInfo:
    """TTS 模型目录。TTS model directory."""
    family, present, missing = _tts_layout(d)
    return ModelInfo(
        kind="tts", id=d.name, name=d.name, path=_rel(d),
        family=family, streaming=False, valid=not missing,
        missing=missing, files=present,
        size_bytes=_dir_size(d), metadata=_load_manifest(d),
    )


def _inspect_llm(path: Path) -> ModelInfo:
    """本地 LLM 文件（本期预留，不加载）。Local LLM file (reserved, not loaded)."""
    files = (path.name,) if _nonempty(path) else ()
    return ModelInfo(
        kind="llm", id=path.stem, name=path.stem, path=_rel(path),
        family="gguf", streaming=False, valid=bool(files),
        missing=() if files else (path.name,),
        files=files, size_bytes=path.stat().st_size if path.is_file() else 0,
    )


def _dir_size(d: Path) -> int:
    """目录内文件总字节数（尽力而为）。Total bytes of files in a directory."""
    total = 0
    try:
        for p in d.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    except OSError:
        pass
    return total


def inspect(kind: str, path: Path | str) -> ModelInfo:
    """校验一个具体路径并返回描述。Inspect one concrete path."""
    p = Path(path)
    if not p.is_absolute():
        p = Path(config.ROOT_DIR) / p
    if kind == "vad":
        return _inspect_vad(p)
    if kind == "kws":
        return _inspect_kws(p)
    if kind == "asr":
        return _inspect_asr(p)
    if kind == "tts":
        return _inspect_tts(p)
    if kind == "llm":
        return _inspect_llm(p)
    raise ValueError(f"未知模型类型: {kind!r}")


def scan(kind: str, *, root: Path | None = None) -> list[ModelInfo]:
    """扫描某能力目录下的全部模型。Scan every model under one capability directory."""
    if kind not in KINDS:
        raise ValueError(f"未知模型类型: {kind!r}（可选 {', '.join(KINDS)}）")
    base = root or kind_root(kind)
    if not base.is_dir():
        return []

    out: list[ModelInfo] = []
    if kind in ("vad", "llm"):
        suffix = ".onnx" if kind == "vad" else ".gguf"
        for p in sorted(base.glob(f"*{suffix}")):
            out.append(inspect(kind, p))
    else:
        for p in sorted(base.iterdir()):
            if p.is_dir():
                out.append(inspect(kind, p))
    return out


def find(kind: str, ref: str | Path) -> ModelInfo | None:
    """按配置里的路径/模型 id 找到模型；找不到返回 None。

    Find a model by the configured path or model id; None when absent.
    """
    ref_s = str(ref or "").strip()
    if not ref_s:
        return None

    # 1) 直接按路径找（绝对或相对项目根）。Direct path (absolute or root-relative).
    p = Path(ref_s)
    if not p.is_absolute():
        p = Path(config.ROOT_DIR) / p
    if p.exists():
        return inspect(kind, p)

    # 2) 直接按模型 id 找（models/<kind>/<id>）。By model id.
    p2 = kind_root(kind) / ref_s
    if p2.exists():
        return inspect(kind, p2)

    # 3) 在已扫描结果里按 id/name 匹配。Match an already-scanned id/name.
    for m in scan(kind):
        if ref_s in (m.id, m.name):
            return m
    return None


def present(kind: str, ref: str | Path) -> bool:
    """纯文件系统判断：模型是否就位且文件齐全。Filesystem-only validity check."""
    m = find(kind, ref)
    return bool(m and m.valid)
