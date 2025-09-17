import importlib.metadata
import os
import time
import uuid
from pathlib import Path
from typing import Any

import jwt
import pytest

# sora_sdk から SoraLoggingSeverity をインポート
from sora_sdk import SoraLoggingSeverity


class Settings:
    def __init__(self, channel_id: str | None = None, signaling_urls: list[str] | None = None):
        # .env ファイルから環境変数を読み込む
        self._load_env_file(".env")

        # 環境変数から設定を読み込む
        # TEST_SIGNALING_URL (単数形) と TEST_SIGNALING_URLS (複数形) の両方をサポート
        signaling_urls_env = os.getenv("TEST_SIGNALING_URLS", os.getenv("TEST_SIGNALING_URL", ""))
        self.signaling_urls = self._parse_signaling_urls(signaling_urls_env)
        self.channel_id_prefix = os.getenv("TEST_CHANNEL_ID_PREFIX", "")
        self.secret = os.getenv("TEST_SECRET_KEY")
        self.api_url = self._parse_api_url(os.getenv("TEST_API_URL"))
        self.openh264_path = os.getenv("OPENH264_PATH")
        self.libwebrtc_log = self._parse_libwebrtc_log(os.getenv("TEST_LIBWEBRTC_LOG"))
        self.channel_id_suffix = str(uuid.uuid4())
        # CLI などから channel_id を明示指定するための上書き値
        self._channel_id_override = channel_id
        # CLI などから signaling_urls を明示指定するための上書き値
        if signaling_urls is not None:
            # 空文字などが混ざっていた場合に備えて軽くフィルタ
            self.signaling_urls = [u.strip() for u in signaling_urls if u and u.strip()]

    def _load_env_file(self, env_file: str) -> None:
        """環境変数ファイルを読み込む"""
        env_path = Path(env_file)
        if not env_path.exists():
            return

        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    # 環境変数が既に設定されていない場合のみ設定
                    if key not in os.environ:
                        os.environ[key] = value

    def _parse_signaling_urls(self, value: str) -> list[str]:
        """TEST_SIGNALING_URLS が , で区切られている場合、それぞれの URL をリストに変換する"""
        if not value:
            return []
        return [x.strip() for x in value.split(",") if x.strip()]

    def _parse_api_url(self, value: str | None) -> str | None:
        """API URLのバリデーション"""
        if not value:
            return None
        # 簡易的なHTTP/HTTPS URLチェック
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError(f"Invalid API URL: {value}")
        return value

    def _parse_libwebrtc_log(self, value: str | None) -> SoraLoggingSeverity | None:
        """libwebrtc_logの値をSoraLoggingSeverityに変換"""
        if not value:
            return None

        match value.lower():
            case "verbose":
                return SoraLoggingSeverity.VERBOSE
            case "info":
                return SoraLoggingSeverity.INFO
            case "warning":
                return SoraLoggingSeverity.WARNING
            case "error":
                return SoraLoggingSeverity.ERROR
            case "none":
                return SoraLoggingSeverity.NONE
            case _:
                # TODO: 未知の値が設定されてたらエラーにした方がいい気がする
                return None

    @property
    def channel_id(self) -> str:
        """TEST_CHANNEL_ID_PREFIX と TEST_CHANNEL_ID_SUFFIX を組み合わせて channel_id を生成する。
        _channel_id_override が設定されている場合はそれを優先する。
        """
        if self._channel_id_override:
            return self._channel_id_override
        return f"{self.channel_id_prefix}_{self.channel_id_suffix}"

    def access_token(self, **kwargs: Any) -> str | None:
        if self.secret is None:
            return None

        payload = {
            "channel_id": self.channel_id,
            # 現在時刻 + 300 秒 (5分)
            "exp": int(time.time()) + 300,
        }
        payload.update(kwargs)

        access_token = jwt.encode(
            payload,
            self.secret,
            algorithm="HS256",
        )

        return access_token


def pytest_report_header(config):
    """pytest の実行時に特定のライブラリのバージョンを追加表示"""
    # config パラメータは pytest から渡されるが、この関数では使用しない
    try:
        version = importlib.metadata.version("sora_sdk")
        return f"sora_sdk: {version}"
    except importlib.metadata.PackageNotFoundError:
        return "sora_sdk: Not installed"


@pytest.fixture
def settings():
    return Settings()
