# -*- coding: utf-8 -*-
"""环境漂移预检(conftest._check_requirements)的单元测试。

Unit tests for the environment-drift preflight in tests/conftest.py: the pins
parser must tolerate comments/options/extras/env markers, and the check must
fail loudly on both a missing package and a version mismatch — these are the
two ways a local environment drifts away from requirements.txt.
"""
import conftest as cf


class TestParsePins:
    def test_extracts_simple_pins(self):
        assert cf._parse_pins("httpx==0.28.1\nfastapi==0.141.1\n") == [
            ("httpx", "0.28.1"),
            ("fastapi", "0.141.1"),
        ]

    def test_skips_comments_blanks_and_options(self):
        text = (
            "# comment\n"
            "\n"
            "-r other.txt\n"
            "--find-links=scripts/libs\n"
            "-e .\n"
            "pypinyin==0.55.0\n"
        )
        assert cf._parse_pins(text) == [("pypinyin", "0.55.0")]

    def test_accepts_extras_and_strips_env_markers(self):
        text = "uvicorn[standard]==0.52.1\npywin32==312; sys_platform == 'win32'\n"
        assert cf._parse_pins(text) == [("uvicorn", "0.52.1"), ("pywin32", "312")]

    def test_ignores_unpinned_lines(self):
        assert cf._parse_pins("requests>=2.0\nflask\n") == []


class TestCheckRequirements:
    def test_passes_on_current_environment(self, monkeypatch):
        """本机若与 requirements 一致(或刚同步过),预检必须放行。"""
        try:
            cf._check_requirements()
        except RuntimeError as exc:  # pragma: no cover - 只在真漂移时触发
            raise AssertionError(f"环境存在漂移,先同步: {exc}") from exc

    def test_fails_on_version_drift(self, monkeypatch):
        """钉 1.2.3 而本机是 9.9.9 → 必须报 version drift。"""
        real_version = cf.metadata.version
        monkeypatch.setattr(
            cf.metadata, "version", lambda name: "9.9.9" if name == "httpx" else real_version(name)
        )
        try:
            cf._check_requirements()
        except RuntimeError as exc:
            assert "httpx==0.28.1" in str(exc)
            assert "9.9.9" in str(exc)
        else:
            raise AssertionError("version drift 未被拦截")

    def test_fails_on_missing_package(self, monkeypatch):
        """本机缺包(如新克隆未装依赖)→ 必须报 not installed。"""

        def fake_version(name):
            if name == "httpx":
                raise cf.metadata.PackageNotFoundError(name)
            return real_version(name)

        real_version = cf.metadata.version
        monkeypatch.setattr(cf.metadata, "version", fake_version)
        try:
            cf._check_requirements()
        except RuntimeError as exc:
            assert "httpx==0.28.1" in str(exc)
            assert "未安装" in str(exc)
        else:
            raise AssertionError("缺包未被拦截")
