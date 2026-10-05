# -*- coding: utf-8 -*-
"""下载通话模式 L1 本地转写模型（k2-fsa 官方 release），只保留推理所需文件。

用法: python scripts/fetch_local_asr_model.py
包体 ~511MB（含 test_wavs/model.pt 等），解包后只保留 tokens.txt + encoder/decoder/
joiner onnx（实测保留集 ~530MB；encoder 单文件 int8 173MB / fp32 315MB，超 GitHub
100MB 单文件限）。按裁决 R9 模型**不入库**（该目录与下载暂存已进 .gitignore），本脚
本是新环境唯一的引导路径，要求可重复执行、可自愈：
- 幂等校验看**全部期望文件**（.fetch-manifest.txt 清单；无清单时退化为 tokens.txt +
  三前缀 onnx 逐项核验），缺 encoder 等半套状态不判「already present」；
- 下载包按预期字节数（511,274,346，GitHub API 实测）校验，中断残留的残缺包跳过前
  即被清掉重下；解包/移动失败也清残包后重抛，下次重跑可恢复（不留裸死锁）。

Download the call-mode L1 local transcription model (official k2-fsa release), keeping
only the inference files. Per ruling R9 the model is NOT committed (gitignored); this
script is the sole bootstrap path for fresh environments, so it must be re-runnable and
self-healing: idempotency checks the complete kept set (manifest, with a tokens+prefix
fallback), the tarball is size-verified (511,274,346 bytes per the GitHub API) so an
interrupted download is discarded and retried, and any extract failure cleans up the
tarball before re-raising.
"""
import shutil
import tarfile
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2"
DEST = ROOT / "models" / "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
TMP = ROOT / "models" / "_asr_download.tar.bz2"
KEEP_PREFIXES = ("encoder-", "decoder-", "joiner-")
# 官方包字节数（GitHub API 实测）；下载前后完整性校验用。
# Official tarball size (measured via the GitHub API); used to verify downloads.
EXPECTED_TARBALL_SIZE = 511274346
# 解包成功后记录的保留文件清单（幂等校验依据）。
# Manifest of kept files, written after a successful extraction (idempotency basis).
MANIFEST = ".fetch-manifest.txt"


def is_complete(dest: Path) -> bool:
    """保留集是否完整——幂等短路的判据（全部期望文件，不只 tokens.txt）。

    有清单 → 逐个核对清单文件；无清单（历史解包/解压中途崩）→ tokens.txt + 三前缀
    各至少一个非空 onnx。半套（如缺 encoder）→ False，触发重解/重下。
    Complete kept-set check (the idempotency gate): manifest entries when present,
    else tokens.txt plus at least one non-empty onnx per prefix. A partial set
    (encoder missing etc.) returns False so the flow re-extracts/redownloads.
    """
    if not (dest / "tokens.txt").is_file():
        return False
    mf = dest / MANIFEST
    if mf.is_file():
        names = [ln.strip() for ln in mf.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not names:
            return False
        return all((dest / n).is_file() and (dest / n).stat().st_size > 0 for n in names)
    return all(
        any(p.stat().st_size > 0 for p in dest.glob(f"{pref}*.onnx"))
        for pref in KEEP_PREFIXES
    )


def _kept_names(dest: Path) -> list[str]:
    """当前保留集文件名（tokens + 三前缀全部非空 onnx）。Names of the kept set."""
    names = ["tokens.txt"] if (dest / "tokens.txt").is_file() else []
    for pref in KEEP_PREFIXES:
        names += sorted(p.name for p in dest.glob(f"{pref}*.onnx") if p.stat().st_size > 0)
    return names


def _tarball_ok() -> bool:
    return TMP.is_file() and TMP.stat().st_size == EXPECTED_TARBALL_SIZE


def main() -> int:
    if is_complete(DEST):
        if not (DEST / MANIFEST).is_file():
            # 迁移历史解包：补写清单，此后按清单逐文件核对。
            # Migrate a pre-manifest extraction: write it now for exact checks later.
            (DEST / MANIFEST).write_text(
                "\n".join(_kept_names(DEST)) + "\n", encoding="utf-8")
        print("already present:", DEST)
        return 0
    DEST.mkdir(parents=True, exist_ok=True)
    try:
        if not _tarball_ok():
            TMP.unlink(missing_ok=True)  # 中断残留的残缺包 → 清掉重下 / discard partial
            print("downloading (511MB, one-time) ...")
            urllib.request.urlretrieve(URL, TMP)
            size = TMP.stat().st_size
            if size != EXPECTED_TARBALL_SIZE:
                raise RuntimeError(f"下载包大小异常: {size} != {EXPECTED_TARBALL_SIZE}")
        print("extracting ...")
        with tarfile.open(TMP, "r:bz2") as tf:
            for m in tf.getmembers():
                name = Path(m.name).name
                if not m.isfile():
                    continue
                if name == "tokens.txt" or any(
                    name.startswith(p) and name.endswith(".onnx") for p in KEEP_PREFIXES
                ):
                    tf.extract(m, path=ROOT / "models")
                    # 包内成员带顶层目录，extract(models/) 后落盘于 models/<topdir>/<name>
                    # Members carry a top dir, so they land in models/<topdir>/ after extract.
                    src = ROOT / "models" / m.name
                    shutil.move(str(src), str(DEST / name))
        if not is_complete(DEST):
            raise RuntimeError(f"解包后保留集仍不完整（{DEST}），请重跑本脚本")
        (DEST / MANIFEST).write_text(
            "\n".join(_kept_names(DEST)) + "\n", encoding="utf-8")
    except Exception:
        TMP.unlink(missing_ok=True)  # 失败自愈：清残包，下次直接重下 / clean up to retry
        raise
    TMP.unlink(missing_ok=True)
    print("done:", sorted(p.name for p in DEST.iterdir() if p.name != MANIFEST))
    return 0


if __name__ == "__main__":
    sys.exit(main())
