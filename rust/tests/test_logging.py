"""libwebrtc ログ制御の到達確認を行う。"""

from __future__ import annotations

import subprocess
import sys

import pytest


def test_logging_self_check() -> None:
    """
    意図・前提・期待値をここに書く
    libwebrtc のログ設定と取得が外部から行えることを確認する。
    前提は初期化が初回だけ有効なため別プロセスで実行すること。
    initialized が真で目印行を取得できることを期待する。
    """
    # 別プロセスで確認する (初期化は初回だけ有効なため)
    code = (
        "import sora_rust_sdk; "
        "result = sora_rust_sdk.logging_self_check(); "
        "assert result['initialized'] is True, result; "
        "assert result['captured'] >= 1, result; "
        "print('ログ制御の到達を確認した')"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as e:
        pytest.fail(f"ログ制御の確認に失敗した: {e.stderr.strip()}")
    print(completed.stdout.strip())
