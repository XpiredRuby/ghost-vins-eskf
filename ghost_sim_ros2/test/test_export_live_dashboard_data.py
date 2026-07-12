import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch


def _load_module():
    serialization = types.ModuleType("rclpy.serialization")
    serialization.deserialize_message = lambda *args, **kwargs: None
    utilities = types.ModuleType("rosidl_runtime_py.utilities")
    utilities.get_message = lambda *args, **kwargs: object
    stubs = {
        "rosbag2_py": types.SimpleNamespace(
            SequentialReader=object,
            StorageOptions=object,
            ConverterOptions=object,
        ),
        "rclpy": types.ModuleType("rclpy"),
        "rclpy.serialization": serialization,
        "rosidl_runtime_py": types.ModuleType("rosidl_runtime_py"),
        "rosidl_runtime_py.utilities": utilities,
    }

    path = Path(__file__).resolve().parents[1] / "tools" / "export_live_dashboard_data.py"
    spec = importlib.util.spec_from_file_location("export_live_dashboard_data", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    with patch.dict(sys.modules, stubs, clear=False):
        spec.loader.exec_module(mod)
    return mod


class _Msg:
    def __init__(self, data):
        self.data = json.dumps(data)


def test_parse_futures_prefers_relative_hypothesis_weight():
    mod = _load_module()
    parsed = mod.parse_futures(1.2, _Msg({
        "visible": False,
        "hypotheses": [{"model": "stationary_hold", "relative_hypothesis_weight": 0.8, "probability": 0.2}],
    }), "mh")

    assert parsed["hypotheses"][0]["relative_hypothesis_weight"] == 0.8
    assert "probability" not in parsed["hypotheses"][0]


def test_parse_futures_accepts_legacy_probability_field():
    mod = _load_module()
    parsed = mod.parse_futures(1.2, _Msg({
        "visible": False,
        "hypotheses": [{"model": "legacy", "probability": 0.35}],
    }), "mh")

    assert parsed["hypotheses"][0]["relative_hypothesis_weight"] == 0.35
