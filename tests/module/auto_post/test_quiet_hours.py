import pytest
from unittest.mock import patch
from datetime import datetime


class TestIsQuietHours:
    def _get_module(self):
        import importlib
        import module.auto_post as ap

        importlib.reload(ap)
        return ap

    def test_disabled_when_start_none(self):
        ap = self._get_module()
        with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_START", None):
            with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_END", 6):
                assert ap.is_quiet_hours() is False

    def test_disabled_when_end_none(self):
        ap = self._get_module()
        with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_START", 23):
            with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_END", None):
                assert ap.is_quiet_hours() is False

    def test_disabled_when_start_equals_end(self):
        ap = self._get_module()
        with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_START", 12):
            with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_END", 12):
                assert ap.is_quiet_hours() is False

    def test_active_inside_range_same_day(self):
        ap = self._get_module()
        with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_START", 10):
            with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_END", 14):
                with patch("module.auto_post.datetime") as mock_dt:
                    mock_dt.utcnow.return_value = datetime(2026, 1, 1, 12, 0)
                    mock_dt.side_effect = lambda *args, **kwargs: datetime(
                        *args, **kwargs
                    )
                    assert ap.is_quiet_hours() is True

    def test_inactive_outside_range_same_day(self):
        ap = self._get_module()
        with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_START", 10):
            with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_END", 14):
                with patch("module.auto_post.datetime") as mock_dt:
                    mock_dt.utcnow.return_value = datetime(2026, 1, 1, 8, 0)
                    mock_dt.side_effect = lambda *args, **kwargs: datetime(
                        *args, **kwargs
                    )
                    assert ap.is_quiet_hours() is False

    def test_active_overnight_range_late_hour(self):
        ap = self._get_module()
        with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_START", 23):
            with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_END", 6):
                with patch("module.auto_post.datetime") as mock_dt:
                    mock_dt.utcnow.return_value = datetime(2026, 1, 1, 23, 30)
                    mock_dt.side_effect = lambda *args, **kwargs: datetime(
                        *args, **kwargs
                    )
                    assert ap.is_quiet_hours() is True

    def test_active_overnight_range_early_hour(self):
        ap = self._get_module()
        with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_START", 23):
            with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_END", 6):
                with patch("module.auto_post.datetime") as mock_dt:
                    mock_dt.utcnow.return_value = datetime(2026, 1, 1, 3, 0)
                    mock_dt.side_effect = lambda *args, **kwargs: datetime(
                        *args, **kwargs
                    )
                    assert ap.is_quiet_hours() is True

    def test_inactive_overnight_range_day_hour(self):
        ap = self._get_module()
        with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_START", 23):
            with patch.object(ap.config, "AUTO_POST_QUIET_HOURS_END", 6):
                with patch("module.auto_post.datetime") as mock_dt:
                    mock_dt.utcnow.return_value = datetime(2026, 1, 1, 12, 0)
                    mock_dt.side_effect = lambda *args, **kwargs: datetime(
                        *args, **kwargs
                    )
                    assert ap.is_quiet_hours() is False
