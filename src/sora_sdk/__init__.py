from .sora_sdk_ext import *  # noqa: F401,F403

# インストールされたパッケージの場合は importlib.metadata から取得
# 開発環境の場合は VERSION ファイルから取得
try:
    from importlib.metadata import version, PackageNotFoundError

    try:
        __version__ = version("sora_sdk")
    except PackageNotFoundError:
        # パッケージがインストールされていない場合（開発環境）
        import os

        _version_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "VERSION"
        )
        if os.path.exists(_version_file):
            with open(_version_file, "r") as f:
                __version__ = f.read().strip()
        else:
            __version__ = "unknown"
except ImportError:
    # Python 3.8 以前の互換性のため
    __version__ = "unknown"

"""
sink はそれぞれ track が必要で参照を保持する必要がある
しかしながら、 sink の C++ 側で shared_ptr として track を持つと、
リファレンスカウンタが正しく処理されず終了時にリークしてしまう。
そのため Python で Wrapper を作り、その中で保持することとした。
"""


class SoraAudioSink(SoraAudioSinkImpl):
    def __init__(self, track, output_frequency, output_channels):
        super().__init__(track, output_frequency, output_channels)
        self.__track = track

    def __del__(self):
        super().__del__()
        del self.__track


class SoraAudioStreamSink(SoraAudioStreamSinkImpl):
    def __init__(self, track, output_frequency, output_channels):
        super().__init__(track, output_frequency, output_channels)
        self.__track = track

    def __del__(self):
        super().__del__()
        del self.__track


class SoraVideoSink(SoraVideoSinkImpl):
    def __init__(self, track):
        super().__init__(track)
        self.__track = track

    def __del__(self):
        super().__del__()
        del self.__track
