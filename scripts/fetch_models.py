# -*- coding: utf-8 -*-
"""下载本地模型到 models/{vad,kws,asr,tts,llm}（幂等、可自愈）。

Download local models into ``models/{vad,kws,asr,tts,llm}`` (idempotent, self-healing).

用法 / Usage::

    python scripts/fetch_models.py --list
    python scripts/fetch_models.py --kind vad
    python scripts/fetch_models.py --kind tts --model kokoro-multi-lang-v1_1
    python scripts/fetch_models.py --kind all

模型体积较大，不入库；KWS 的小模型随仓库提供（无需下载）。
Large models are not committed; the small KWS model ships with the repo.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
TMP = MODELS / "_download.bin"


@dataclass(frozen=True)
class ModelSpec:
    """一个可下载模型的描述。One downloadable model's description."""

    kind: str
    model: str
    url: str
    size: int
    archive: bool = False
    keep_prefixes: tuple[str, ...] = ()
    keep_names: tuple[str, ...] = ()


SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        kind="vad", model="ten-vad.onnx",
        url="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/ten-vad.onnx",
        size=332211,
    ),
    ModelSpec(
        kind="vad", model="silero_vad.onnx",
        url="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx",
        size=643854,
    ),
    ModelSpec(
        kind="asr", model="sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23",
        url="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
            "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23.tar.bz2",
        size=74004050, archive=True,
        keep_prefixes=("encoder-", "decoder-", "joiner-"),
        keep_names=("tokens.txt",),
    ),
    ModelSpec(
        kind="asr", model="sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20",
        url="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
            "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2",
        size=511274346, archive=True,
        keep_prefixes=("encoder-", "decoder-", "joiner-"),
        keep_names=("tokens.txt",),
    ),
    ModelSpec(
        kind="tts", model="kokoro-multi-lang-v1_1",
        url="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
            "kokoro-multi-lang-v1_1.tar.bz2",
        size=364816464, archive=True,
    ),
)


def _present(spec: ModelSpec) -> bool:
    """目标是否已就位（文件系统判断）。Whether the target is already present."""
    dest = MODELS / spec.kind / spec.model
    if spec.archive:
        if spec.kind == "asr":
            return dest.is_dir() and (dest / "tokens.txt").is_file() and all(
                any(p.stat().st_size > 0 for p in dest.glob(f"{pref}*.onnx"))
                for pref in spec.keep_prefixes
            )
        return dest.is_dir() and any(dest.iterdir())
    return dest.is_file() and dest.stat().st_size == spec.size


def _download(spec: ModelSpec) -> None:
    """下载并解包一个模型。Download and extract one model."""
    MODELS.mkdir(parents=True, exist_ok=True)
    dest = MODELS / spec.kind / spec.model
    if _present(spec):
        print(f"already present: {dest}")
        return

    if TMP.is_file() and TMP.stat().st_size == spec.size:
        print("reusing downloaded archive ...")
    else:
        TMP.unlink(missing_ok=True)
        print(f"downloading {spec.size / 1024 / 1024:.0f} MB: {spec.url}")
        urllib.request.urlretrieve(spec.url, TMP)
        got = TMP.stat().st_size
        if got != spec.size:
            TMP.unlink(missing_ok=True)
            raise RuntimeError(f"下载大小异常: {got} != {spec.size}")
    if not spec.archive:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(TMP), str(dest))
        print("done:", dest)
        return

    print("extracting ...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(TMP, "r:bz2") as tf:
        members = [m for m in tf.getmembers() if m.isfile() and not m.name.startswith("__MACOSX")]
        if spec.keep_names or spec.keep_prefixes:
            members = [
                m for m in members
                if Path(m.name).name in spec.keep_names
                or any(Path(m.name).name.startswith(p) and Path(m.name).name.endswith(".onnx")
                       for p in spec.keep_prefixes)
            ]
        dest.mkdir(parents=True, exist_ok=True)
        for m in members:
            src = tf.extractfile(m)
            if src is None:
                continue
            if spec.keep_names or spec.keep_prefixes:
                # ASR 只保留少量文件，平铺到模型目录。ASR keeps only a flat file set.
                rel = Path(Path(m.name).name)
            else:
                # 完整模型（如 Kokoro）保留 tarball 内的相对结构——espeak-ng-data 是目录，
                # 平铺会把目录结构打散，registry 就判模型不完整。
                # Full models keep their relative layout; flattening would destroy
                # espeak-ng-data/ and make the registry report an incomplete model.
                parts = Path(m.name).parts
                rel = Path(*parts[1:]) if len(parts) > 1 else Path(parts[0])
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    TMP.unlink(missing_ok=True)
    print("done:", dest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下载本地语音模型")
    parser.add_argument("--kind", choices=("vad", "asr", "tts", "kws", "llm", "all"), default="all")
    parser.add_argument("--model", default="", help="只下载指定模型 id/文件名")
    parser.add_argument("--list", action="store_true", help="列出可下载模型")
    args = parser.parse_args(argv)

    if args.list:
        for s in SPECS:
            print(f"{s.kind:4} {s.model:60} {s.size / 1024 / 1024:8.1f} MB")
        return 0

    chosen = [
        s for s in SPECS
        if (args.kind in ("all", s.kind)) and (not args.model or args.model == s.model)
    ]
    if not chosen:
        print("没有匹配的模型；KWS 小模型随仓库提供，LLM 本期不接本地推理。")
        return 0
    for s in chosen:
        _download(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
