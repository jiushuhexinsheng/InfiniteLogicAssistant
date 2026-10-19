# TTS 模型

放置 sherpa-onnx 语音合成模型目录，默认使用 Kokoro：

- `kokoro-multi-lang-v1_1/`（或 v1_0）
- 目录内通常包含 `model.onnx`、`voices.bin`、`tokens.txt`、`espeak-ng-data/`、`lexicon-*.txt`

由 `voice.tts.local.model_dir` 指向具体目录。
