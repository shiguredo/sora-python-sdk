import os
import sora_sdk


def test_version():
    """sora_sdk.__version__ が取得できることを確認"""
    assert hasattr(sora_sdk, "__version__")
    assert isinstance(sora_sdk.__version__, str)
    assert sora_sdk.__version__ != "unknown"

    # VERSION ファイルの内容と一致することを確認
    version_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "VERSION")
    with open(version_file, "r") as f:
        expected_version = f.read().strip()

    assert sora_sdk.__version__ == expected_version
    print(f"sora_sdk.__version__ = {sora_sdk.__version__}")
