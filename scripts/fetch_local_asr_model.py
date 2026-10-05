# -*- coding: utf-8 -*-
"""下载通话模式 L1 本地转写模型（k2-fsa 官方 release），只保留推理所需文件。

用法: python scripts/fetch_local_asr_model.py
包体 ~511MB（含 test_wavs/model.pt 等），解包后只留 tokens.txt + encoder/decoder/joiner
onnx（~90MB）入库，tar.bz2 用完即删。

Download the call-mode L1 local transcription model (official k2-fsa release), keeping
only the inference files. The tarball is ~511MB; only tokens.txt + encoder/decoder/joiner
onnx (~90MB) are kept and committed; the tarball is deleted afterwards.
"""
import shutil
import tarfile
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2"
DEST = ROOT / "models" / "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
KEEP_PREFIXES = ("encoder-", "decoder-", "joiner-")


def main() -> int:
    if (DEST / "tokens.txt").is_file():
        print("already present:", DEST)
        return 0
    DEST.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / "models" / "_asr_download.tar.bz2"
    if not tmp.is_file():
        print("downloading (511MB, one-time) ...")
        urllib.request.urlretrieve(URL, tmp)
    print("extracting ...")
    with tarfile.open(tmp, "r:bz2") as tf:
        for m in tf.getmembers():
            name = Path(m.name).name
            if not m.isfile():
                continue
            if name == "tokens.txt" or any(name.startswith(p) and name.endswith(".onnx") for p in KEEP_PREFIXES):
                tf.extract(m, path=ROOT / "models")
                # 包内成员带顶层目录，extract(models/) 后落盘于 models/<topdir>/<name>
                # Members carry a top dir, so they land in models/<topdir>/ after extract.
                src = ROOT / "models" / m.name
                shutil.move(str(src), str(DEST / name))
    tmp.unlink(missing_ok=True)
    print("done:", sorted(p.name for p in DEST.iterdir()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
