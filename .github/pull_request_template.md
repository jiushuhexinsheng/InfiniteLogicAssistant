## 变更说明

<!-- 这个 PR 做了什么、为什么。What changed and why. -->

## 检查清单

- [ ] 后端测试：`python -m pytest tests/ -q`
- [ ] 类型检查：`python -m mypy core/ server.py`
- [ ] Lint：`ruff check core/ server.py main.py cli/`
- [ ] 前端测试：`npm --prefix web test`
- [ ] 前端类型 + 构建：`npm --prefix web run build`
- [ ] **文档对账**：改了路由/配置/上传口径时，README 与 wiki 已同步
      （`python -m pytest tests/test_docs_consistency.py -q`）
- [ ] 改了后端 schema：`python scripts/gen_openapi.py` 无漂移
