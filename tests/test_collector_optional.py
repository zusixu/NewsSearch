"""
tests/test_collector_optional.py

Tests for CopilotResearchCollector optional enable/disable behaviour.

Coverage:
- is_enabled() returns True when sources_config.copilot_research = True
- is_enabled() returns False when sources_config.copilot_research = False
- is_enabled() returns True when sources_config has no copilot_research attr (backward compat)
- _create_collectors() does NOT instantiate CopilotResearchCollector when copilot_research=False
- _create_collectors() DOES instantiate CopilotResearchCollector when copilot_research=True
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.collectors.base import RunContext
from app.collectors.copilot_research_collector import CopilotResearchCollector


# ---------------------------------------------------------------------------
# is_enabled() contract
# ---------------------------------------------------------------------------

class TestCopilotResearchIsEnabled:
    """Tests for CopilotResearchCollector.is_enabled() behaviour."""

    def test_enabled_when_config_true(self):
        """is_enabled() returns True when copilot_research=True."""
        class _Cfg:
            copilot_research = True

        c = CopilotResearchCollector()
        assert c.is_enabled(_Cfg()) is True

    def test_disabled_when_config_false(self):
        """is_enabled() returns False when copilot_research=False."""
        class _Cfg:
            copilot_research = False

        c = CopilotResearchCollector()
        assert c.is_enabled(_Cfg()) is False

    def test_enabled_when_no_attribute(self):
        """is_enabled() returns True when config has no copilot_research attr."""
        c = CopilotResearchCollector()
        # None
        assert c.is_enabled(None) is True
        # Object without the attribute
        class _CfgNoAttr:
            pass
        assert c.is_enabled(_CfgNoAttr()) is True

    def test_enabled_with_truthy_non_bool(self):
        """is_enabled() coerces truthy values to True."""
        class _Cfg:
            copilot_research = 1  # truthy int

        c = CopilotResearchCollector()
        assert c.is_enabled(_Cfg()) is True

    def test_disabled_with_falsy_non_bool(self):
        """is_enabled() coerces falsy values to False."""
        class _Cfg:
            copilot_research = 0  # falsy int

        c = CopilotResearchCollector()
        # bool(0) is False
        assert c.is_enabled(_Cfg()) is False


# ---------------------------------------------------------------------------
# _create_collectors() integration
# ---------------------------------------------------------------------------

class TestCreateCollectorsIntegration:
    """Tests for _create_collectors() vis-a-vis CopilotResearchCollector."""

    @pytest.fixture
    def mock_config_copilot_true(self):
        """Create a mock AppConfig with copilot_research=True."""
        config = MagicMock()
        config.sources.akshare = False
        config.sources.web = False
        config.sources.copilot_research = True
        config.storage.raw_dir = "data/raw"
        return config

    @pytest.fixture
    def mock_config_copilot_false(self):
        """Create a mock AppConfig with copilot_research=False."""
        config = MagicMock()
        config.sources.akshare = False
        config.sources.web = False
        config.sources.copilot_research = False
        config.storage.raw_dir = "data/raw"
        return config

    def test_copilot_instantiated_when_config_true(self, mock_config_copilot_true):
        """_create_collectors() includes CopilotResearchCollector when enabled."""
        from app.main import _create_collectors
        from app.collectors.copilot_research_collector import CopilotResearchCollector

        collectors = _create_collectors(mock_config_copilot_true, override=None)

        copilot_collectors = [
            c for c in collectors if isinstance(c, CopilotResearchCollector)
        ]
        assert len(copilot_collectors) == 1

    def test_copilot_not_instantiated_when_config_false(self, mock_config_copilot_false):
        """_create_collectors() omits CopilotResearchCollector when disabled."""
        from app.main import _create_collectors
        from app.collectors.copilot_research_collector import CopilotResearchCollector

        collectors = _create_collectors(mock_config_copilot_false, override=None)

        copilot_collectors = [
            c for c in collectors if isinstance(c, CopilotResearchCollector)
        ]
        assert len(copilot_collectors) == 0

    def test_copilot_not_instantiated_defaults_false(self):
        """_create_collectors() omits CopilotResearchCollector when config
        reads copilot_research=False (the default from config.yaml)."""
        from app.main import _create_collectors
        from app.collectors.copilot_research_collector import CopilotResearchCollector

        config = MagicMock()
        config.sources.akshare = False
        config.sources.web = False
        config.sources.copilot_research = False
        config.storage.raw_dir = "data/raw"

        collectors = _create_collectors(config, override=None)

        copilot_collectors = [
            c for c in collectors if isinstance(c, CopilotResearchCollector)
        ]
        assert len(copilot_collectors) == 0
