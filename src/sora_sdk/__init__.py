from .sora_sdk_ext import *  # noqa: F401,F403

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
