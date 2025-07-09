import importlib.metadata
import time
import uuid
from typing import Annotated

import jwt
import pytest
from pydantic import Field, HttpUrl, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# sora_sdk から SoraLoggingSeverity をインポート
from sora_sdk import SoraLoggingSeverity


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix=".env", env_file_encoding="utf-8")

    # TODO: list[WebsocketUrl] 型にする
    signaling_urls: Annotated[list[str], NoDecode] = Field(default=[], alias="TEST_SIGNALING_URLS")
    channel_id_prefix: str = Field(default="", alias="TEST_CHANNEL_ID_PREFIX")
    secret: SecretStr | None = Field(default=None, alias="TEST_SECRET_KEY")
    api_url: HttpUrl | None = Field(default=None, alias="TEST_API_URL")
    # TODO: openh264_path は FilePath 型にする
    openh264_path: str | None = Field(default=None, alias="OPENH264_PATH")
    libwebrtc_log: SoraLoggingSeverity | None = Field(default=None, alias="TEST_LIBWEBRTC_LOG")

    channel_id_suffix: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @field_validator("signaling_urls", mode="before")
    @classmethod
    def validate_signaling_urls(cls, v: str) -> list[str]:
        """
        TEST_SIGNALING_URLS が , で区切られている場合、それぞれの URL をリストに変換する
        """
        return [x.strip() for x in v.split(",")]

    @field_validator("libwebrtc_log", mode="before")
    @classmethod
    def validate_libwebrtc_log(cls, v: str | None) -> SoraLoggingSeverity | None:
        if v is None:
            return None

        match v.lower():
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
                # TODO: 道の値が設定されてたらエラーにした方がいい気がする
                return None

    @computed_field
    @property
    def channel_id(self) -> str:
        """
        TEST_CHANNEL_ID_PREFIX と TEST_CHANNEL_ID_SUFFIX を組み合わせて channel_id を生成する
        """
        return f"{self.channel_id_prefix}_{self.channel_id_suffix}"

    def access_token(self, **kwargs) -> str | None:
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
            self.secret.get_secret_value(),
            algorithm="HS256",
        )

        return access_token


def pytest_report_header(config):
    """pytest の実行時に特定のライブラリのバージョンを追加表示"""
    try:
        version = importlib.metadata.version("sora_sdk")
        return f"sora_sdk: {version}"
    except importlib.metadata.PackageNotFoundError:
        return "sora_sdk: Not installed"


@pytest.fixture
def settings():
    return Settings()
