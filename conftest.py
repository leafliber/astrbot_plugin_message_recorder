"""Root conftest - 在所有测试收集之前注入 astrbot mock"""

import sys
import types
from unittest.mock import MagicMock


def _create_mock_astrbot_modules():
    if "astrbot.api" in sys.modules:
        return

    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api_event = types.ModuleType("astrbot.api.event")
    api_star = types.ModuleType("astrbot.api.star")
    core = types.ModuleType("astrbot.core")
    core_utils = types.ModuleType("astrbot.core.utils")
    core_path = types.ModuleType("astrbot.core.utils.astrbot_path")

    api.logger = MagicMock()
    api.AstrBotConfig = MagicMock

    api_event.filter = MagicMock()
    api_event.AstrMessageEvent = MagicMock

    api_star.Context = MagicMock
    api_star.Star = MagicMock
    api_star.register = lambda **kwargs: lambda cls: cls

    core_path.get_astrbot_data_path = lambda: "/tmp/astrbot_test/data"
    core_path.get_astrbot_plugin_data_path = lambda: "/tmp/astrbot_test/data/plugin_data"

    astrbot.api = api
    astrbot.core = core
    api.event = api_event
    api.star = api_star
    core.utils = core_utils
    core_utils.astrbot_path = core_path

    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = api_event
    sys.modules["astrbot.api.star"] = api_star
    sys.modules["astrbot.core"] = core
    sys.modules["astrbot.core.utils"] = core_utils
    sys.modules["astrbot.core.utils.astrbot_path"] = core_path


_create_mock_astrbot_modules()
