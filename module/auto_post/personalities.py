import os
import logging
from typing import Optional
import yaml

logger = logging.getLogger(__name__)

_config: Optional[dict] = None


def _load_config() -> dict:
    global _config
    if _config is None:
        config_path = os.path.join(os.path.dirname(__file__), "channel_config.yaml")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                _config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Channel config not found at {config_path}")
            _config = {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing channel config: {e}")
            _config = {}
    return _config


def get_channel_focus(channel_key: str) -> str:
    channels = _load_config().get("channels", {})
    channel_config = channels.get(channel_key, {})
    return channel_config.get("content_focus", "")


def get_all_channels() -> list[str]:
    return list(_load_config().get("channels", {}).keys())
