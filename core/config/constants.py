# -*- coding: utf-8 -*-
"""配置常量与路径（core/config/ 包内共享）。"""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = ROOT_DIR / "config.yaml"
EXAMPLE_FILE = ROOT_DIR / "config.yaml.example"
SECRETS_FILE = ROOT_DIR / "config.secrets.yaml"
SECRETS_EXAMPLE = ROOT_DIR / "config.secrets.yaml.example"

# 各段密钥对应的全局环境变量名（config.secrets.yaml 段内 api_key 的兜底 env）
_ENV_KEY_MAP = {
    "llm": "LLM_API_KEY",
    "asr": "ASR_API_KEY",
    "tts": "TTS_API_KEY",
}
