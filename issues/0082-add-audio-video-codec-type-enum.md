# create_connection の音声・映像コーデックタイプに Enum を提供する

- Created: 2026-09-11
- Completed: -
- Branch: feature/add-audio-video-codec-type-enum
- Polished: -
- Reporter: @voluntas

## 目的

`Sora.create_connection()` の `audio_codec_type` / `video_codec_type` は `str` でしか指定できず、typo や未対応の値が Sora への接続時まで検出されない。Enum を提供してエディタ補完と静的型チェックを効かせ、指定可能な値と表記揺れをなくす。

## 現状

- `src/sora_sdk/sora_sdk_ext.pyi` の `Sora.create_connection` は `audio_codec_type: Optional[str] = None` と `video_codec_type: Optional[str] = None` を受け取る。
- `src/sora.cpp` の `Sora::CreateConnection` は `std::optional<std::string>` で受け取り、`sora::SoraSignalingConfig::audio_codec_type` / `video_codec_type` にそのまま渡している。C++ SDK 側のフィールドも `std::string` である (`_install/<platform>/sora/include/sora/sora_signaling.h`)。
- `src/sora_sdk_ext.cpp` には `SoraVideoCodecType` (`webrtc::VideoCodecType` を `nb::is_arithmetic()` で公開した `enum.IntEnum`) が既にある。ただしこれは `Sora()` の `video_codec_preference` と `get_video_codec_capability()` のためのもので、`create_connection()` の `video_codec_type` は受け付けない。音声側の enum は存在しない。
- テストは `video_codec_type="H264"`、`audio_codec_type="OPUS"` のように `str` で渡している。`tests/client.py` の `codec_type_string_to_codec_type()` は文字列を `SoraVideoCodecType` へ変換しており、文字列と enum が併用されている。

## 設計方針

- 音声は `SoraAudioCodecType` を追加する。値は Sora が受け付ける音声コーデック (`OPUS`) とし、`str` の部分型 (`enum.StrEnum`) にする。`str` の部分型であれば `create_connection()` の `std::optional<std::string>` 引数にそのまま渡せるため、C++ 側に音声用の変換を追加する必要がない。
- 映像は既存の `SoraVideoCodecType` を `create_connection()` の `video_codec_type` でも受け付ける。同じ意味の enum を二重に増やさない。
- `create_connection()` の `video_codec_type` / `audio_codec_type` は `str` も引き続き受け付ける。後方互換を壊さない。
- `SoraVideoCodecType` は `int` ベース (`webrtc::VideoCodecType`) なので `str` としてそのまま渡せない。`src/sora.cpp` の `Sora::CreateConnection` で受け取った `SoraVideoCodecType` を対応するシグナリング文字列 (`VP8` / `VP9` / `H264` / `H265` / `AV1`) へ変換してから `config.video_codec_type` に設定する。
- 新たに追加する enum も引数も SDK の接頭辞に合わせて `Sora` を付ける。

## 完了条件

- `Sora.create_connection(audio_codec_type=SoraAudioCodecType.OPUS)` が受け付けられること。
- `Sora.create_connection(video_codec_type=SoraVideoCodecType.H264)` が受け付けられ、シグナリングに `H264` が送られること。
- `audio_codec_type="OPUS"` / `video_codec_type="H264"` の `str` 指定が引き続き動作すること。
- `Sora.create_connection` の pyi の型が `Optional[str | SoraAudioCodecType]` / `Optional[str | SoraVideoCodecType]` に更新されていること。
- 実 Sora に対する接続テストで、enum 指定と文字列指定の両方が通ること。
- CHANGES.md の `## develop` に `[ADD]` エントリが追記されていること。

## 解決方法

1. `src/sora_sdk_ext.cpp` に `SoraAudioCodecType` (`enum.StrEnum` 相当、`OPUS`) を追加する。
2. `Sora.create_connection` の `audio_codec_type` / `video_codec_type` 引数を `str` と enum の両方を受け付けられるようにし、`video_codec_type` は `SoraVideoCodecType` をシグナリング文字列へ変換する。
3. `src/sora.cpp` の `Sora::CreateConnection` を新しい引数型に合わせ、未知の値はエラーにする。
4. `tests/client.py` と各テストを enum 指定に更新し、enum と文字列の両方で接続できることを確認する。
5. CHANGES.md の `## develop` に `[ADD]` エントリを追記する。
