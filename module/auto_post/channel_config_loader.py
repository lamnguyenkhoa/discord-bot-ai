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


def get_channel_config(channel_key: str) -> dict:
    channels = _load_config().get("channels", {})
    channel_config = channels.get(channel_key, {})
    directives = channel_config.get("prompt_directives", [])
    if isinstance(directives, str):
        directives = [directives]
    return {
        "prompt_directives": directives,
        "context_addition": channel_config.get("context_addition", ""),
        "capture_to_mem0": channel_config.get("capture_to_mem0", False),
    }


def get_all_channels() -> list[str]:
    return list(_load_config().get("channels", {}).keys())
