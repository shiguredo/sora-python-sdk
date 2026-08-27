# `SoraConnection` 等のコールバック群を public のまま外部に晒している状態を private に閉じる

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-sora-connection-callbacks-private
- Polished: 2026-07-30

## 目的

`SoraConnection` クラスでは Python 側からコールバックを設定するために `on_signaling_message_` / `on_set_offer_` / `on_ws_close_` / `on_disconnect_` / `on_notify_` / `on_push_` / `on_message_` / `on_rpc_` / `on_switched_` / `on_track_` / `on_data_channel_` のメンバ変数群がクラスの `public:` セクションに直接置かれている。nanobind の `def_rw` でこのメンバを外向けに公開しているため、「C++ 側から見た内部状態」と「Python 側に公開している API 表面」が等しくなってしまい、C++ 内部のリファクタリングが Python 側の API 互換を必ず巻き込む状態になっている。

同様に `SoraAudioStreamSinkImpl::on_frame_` / `SoraVideoSinkImpl::on_frame_` / `SoraAudioSinkImpl::on_data_` / `SoraAudioSinkImpl::on_format_` も public に置かれ `def_rw` で公開されている。

このまま放置すると、内部実装の進化と外向け API の互換維持が分離できず、API 進化が強く阻害される。public 露出と internal 実装を分離する。

## 優先度根拠

Medium とする。

- 動作上のバグではないため High ではない。
- ただし「C++ 内部のメンバを直接 public で晒している」状態は API 進化を強く阻害する。例えば「コールバックの引数を増やしたい」「コールバック登録時の前提条件を変えたい」と思った瞬間、Python ABI 互換を考慮しないと触れない。今のうちに accessor 経由に切り替えておくと、後から弁明的な互換レイヤを足す必要が減る。
- 修正は機械的だが範囲が C++ クラス本体 + nanobind バインディングにまたがるため、Low では片付かない。

## 現状

### `SoraConnection` のコールバック群が public

`src/sora_connection.h` の `SoraConnection` クラスで、`on_signaling_message_` 以下の `std::function` メンバ群がすべて `public:` 領域に置かれている:

```cpp
// sora::SoraSignalingObserver のコールバック関数が呼び出された時に対応して呼び出す Python の関数を保持する
std::function<
    void(sora::SoraSignalingType, sora::SoraSignalingDirection, std::string)>
    on_signaling_message_;
std::function<void(std::string)> on_set_offer_;
std::function<void(int, std::string)> on_ws_close_;
std::function<void(sora::SoraSignalingErrorCode, std::string)> on_disconnect_;
std::function<void(std::string)> on_notify_;
std::function<void(std::string)> on_push_;
std::function<void(std::string, nb::bytes)> on_message_;
std::function<void(nb::bytes)> on_rpc_;
std::function<void(std::string)> on_switched_;
std::function<void(nb::ref<SoraMediaTrack>)> on_track_;
std::function<void(std::string)> on_data_channel_;
```

nanobind の `def_rw` で Python から直接代入されている (`src/sora_sdk_ext.cpp` の `SoraConnection` バインディング箇所)。

### `SoraAudioStreamSinkImpl` / `SoraVideoSinkImpl` のコールバックが public

`src/sora_audio_stream_sink.h` の `SoraAudioStreamSinkImpl::on_frame_` と `src/sora_video_sink.h` の `SoraVideoSinkImpl::on_frame_` も同様に public に置かれ、`def_rw("on_frame", ...)` で公開されている。

### `SoraAudioSinkImpl` の廃止予定コールバック

`src/sora_audio_sink.h` の `SoraAudioSinkImpl` クラスで `on_data_` / `on_format_` が public に置かれている:

```cpp
/**
 * 実装上の留意点：コールバックと Read 関数の共存はパフォーマンスや使い方の面で難しいことが判明したので、
 * on_data_, on_format_ ともに廃止予定です。
*/
std::function<void(nb::ndarray<nb::numpy, int16_t, nb::shape<-1, -1>>)>
    on_data_;
std::function<void(int, size_t)> on_format_;
```

「廃止予定」とコメントには書いてあるが、`[[deprecated]]` 等のマーカーは無く、Python 側からも廃止予定であることが分からない。

## 設計方針

C++ 内部メンバと Python 公開 API を分離する。shiguredo-python 規約「後方互換性は考慮しないこと」に従い、Python 側の API 表面は変更してよい。

1. `SoraConnection` の `on_*` メンバを `private:` に移し、nanobind 側は `def_prop_rw` (getter/setter ラムダ経由) で公開する。Python 側からは `connection.on_track = callable` のプロパティ代入で設定できる形を維持するが、C++ 内部のメンバ名・型は自由に変更できるようになる。
2. `SoraAudioStreamSinkImpl::on_frame_` / `SoraVideoSinkImpl::on_frame_` も同様に `private:` に移し `def_prop_rw` で公開する。
3. `SoraAudioSinkImpl::on_data_` / `on_format_` は廃止予定のため、`private:` 化に加えて setter 内で `DeprecationWarning` を送出する (Python の `warnings.warn` 相当。nanobind から `PyErr_WarnEx` を使う)。C++ 側にも `[[deprecated("Use Read() instead")]]` を付与する。
4. CHANGES.md の `## develop` セクションに、`SoraAudioSinkImpl` の `on_data` / `on_format` プロパティが非推奨になったことを `[CHANGE]` で記載する。

## 完了条件

- `SoraConnection` / `SoraAudioStreamSinkImpl` / `SoraVideoSinkImpl` / `SoraAudioSinkImpl` のコールバックメンバがすべて `private:` に置かれ、外部からは `def_prop_rw` の accessor 経由でのみ設定できる構造になっていること。
- `SoraAudioSinkImpl` の `on_data` / `on_format` setter で `DeprecationWarning` が送出されること。
- CHANGES.md に非推奨化のエントリが記載されていること。
- 既存テストが通ること。
