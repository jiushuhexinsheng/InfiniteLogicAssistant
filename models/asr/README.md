# ASR 模型

放置 sherpa-onnx 语音识别模型目录。当前默认（流式 Zipformer）由以下脚本下载：

```bash
python scripts/fetch_local_asr_model.py
```

模型目录应包含 `tokens.txt` 与 encoder/decoder/joiner ONNX 文件。
可放入任意兼容的 sherpa-onnx 模型；registry 会识别是否支持流式输出。
