# -*- coding: utf-8 -*-
"""LLM 模型清单与全局模型切换的响应模型。LLM catalogue / active-model response models."""

from pydantic import BaseModel, Field

from .base import ApiResponse


class LlmActive(BaseModel):
    """当前全局使用的供应商与模型。The globally active provider and model."""

    provider: str = ""
    model: str = ""


class LlmModelGroup(BaseModel):
    """一个供应商分组及其可选模型。One provider group and its selectable models."""

    provider: str
    label: str
    models: list[str] = Field(default_factory=list)
    current_model: str = ""


class LlmModelsResponse(ApiResponse):
    """`GET /api/llm/models` 响应。Response of GET /api/llm/models."""

    active: LlmActive = Field(default_factory=LlmActive)
    groups: list[LlmModelGroup] = Field(default_factory=list)


class SetActiveModelRequest(BaseModel):
    """`POST /api/llm/active-model` 请求体。Request body of the active-model endpoint."""

    provider: str
    model: str


class SetActiveModelResponse(ApiResponse):
    """`POST /api/llm/active-model` 响应。Response of the active-model endpoint."""

    active: LlmActive = Field(default_factory=LlmActive)
