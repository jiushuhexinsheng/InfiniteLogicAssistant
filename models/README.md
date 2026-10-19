# 本地模型目录

模型按能力分类，每个能力一个目录。运行时由 `core/voice/local/sherpa_onnx/registry.py`
扫描并校验，**不要求在代码里注册模型名**：把任意兼容 sherpa-onnx 的模型目录放进对应
能力目录，刷新设置页的模型列表即可选择。

```text
models/
  vad/   # 语音活动检测：ten-vad.onnx / silero_vad.onnx（单文件）
  kws/   # 关键词检测：tokens.txt + encoder/decoder/joiner onnx
  asr/   # 语音识别：tokens.txt + encoder/decoder/joiner onnx（或其它 sherpa 支持的结构）
  tts/   # 语音合成：Kokoro / VITS / Matcha 等 sherpa-onnx 模型目录
  llm/   # 预留：本地 LLM（本期不接线，LLM 仍走 API）
```

规则：

- 大模型不入库，由 `scripts/fetch_models.py` 下载，或手动放入；
- 小模型（KWS 3.3M）随仓库入库；
- 每个模型目录可选放一个 `model.json` 描述 family / streaming / 文件清单；
  没有时由 registry 按文件名特征推断；
- 设置页只做文件系统校验，**不会为了显示一个勾选而把模型载入内存**。
