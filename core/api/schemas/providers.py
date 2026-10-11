# -*- coding: utf-8 -*-
"""获取模型列表端点响应。Fetch-models response.

厂商目录端点（GET /api/providers）已随目录退役。The catalogue endpoint retired
together with the vendor catalogue.
"""



from .base import ApiResponse


class FetchModelsResponse(ApiResponse):
    """获取模型列表端点响应。

    ``/api/providers/fetch-models`` fetch response.
    """
    models: list[str] = []
    count: int = 0
