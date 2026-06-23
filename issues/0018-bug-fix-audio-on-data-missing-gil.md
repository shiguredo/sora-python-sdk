# `SoraAudioSinkImpl::AppendData` と `SoraAudioStreamSinkImpl::OnData` で GIL を取得せずに Python コールバックを呼んでいる問題を修正する

- Priority: High
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-audio-on-data-missing-gil

## 目的

`SoraAudioSinkImpl::AppendData` の `on_format_` / `on_data_` 呼び出しと、`SoraAudioStreamSinkImpl::OnData` の `on_frame_` 呼び出しは、libwebrtc のオーディオワーカースレッド (GIL 非保持) から発火する。`call_python` 経由で Python の `std::function` を呼び、内部で `nb::ndarray` の構築・Python 参照カウント操作・例外 throw を行っている。GIL を保持していない状態で Python C-API を触ると未定義動作になり、Python オブジェクトのメモリ破壊・SIGSEGV に至る。

`pending/0013-bug-fix-append-data-callback-missing-gil.md` で同じ問題が pending 状態のまま方針未確定で残っており、本 issue で正式に対応方針を確定して修正する。pending/0013 は本 issue の close と同時に closed 化する。

## 優先度根拠

High とする。

- libwebrtc 側で確実に発生する経路で、`on_data_` / `on_format_` / `on_frame_` を Python 側で設定すればクラッシュ可能。
- 同種の bug (`closed/0009-bug-fix-on-push-missing-gil.md` 等) が既に修正されており、未対応で残るのはここだけ。
- 正式リリース前に方針確定して修正しないと、`SoraAudioStreamSink` を用いる Encoded Transform / VAD 利用者で SEGV が出る。

## 現状

### `SoraAudioSinkImpl`

`src/sora_audio_sink.cpp:103-135` `AppendData`:

```cpp
void SoraAudioSinkImpl::AppendData(const int16_t* audio_data, ...) {
  {
    std::unique_lock<std::mutex> lock(buffer_mtx_);
    ...
    if (on_format_) {
      call_python(on_format_, sample_rate_, number_of_channels_);
    }
    ...
  }

  if (on_data_) {
    size_t shape[2] = {number_of_frames, number_of_channels_};
    auto data = nb::ndarray<nb::numpy, int16_t, nb::shape<-1, -1>>(
        (void*)audio_data, 2, shape, nb::handle());
    call_python(on_data_, data);
  }
}
```

`OnData` (`src/sora_audio_sink.cpp:52-101`) は `webrtc::AudioTrackSinkInterface::OnData` で、libwebrtc のオーディオキャプチャ/再生スレッドから呼ばれる。GIL は保持されていない。

### `SoraAudioStreamSinkImpl`

`src/sora_audio_stream_sink.cpp:209`:

```cpp
call_python(on_frame_,
            std::make_shared<SoraAudioFrame>(std::move(tuned_frame)));
```

これも `webrtc::AudioTrackSinkInterface::OnData` 経由なので同じ条件下。

### 比較: video sink の正しい例

`src/sora_video_sink.cpp:102-114` では同種の問題を `PostTask` 経由でワーカースレッドに飛ばし、ワーカー内で `gil_scoped_acquire acq;` を取得してから `call_python` を呼ぶ実装になっている。オーディオ側だけこの対策が抜けている。

### `call_python` の責務

`src/sora_call.h:12-26` の `call_python` は `f(args...)` を呼ぶラッパーで、内部では GIL 取得を行わない。呼び出し側が GIL を保持していることが前提。

### `pending/0013` の存在

`issues/pending/0013-bug-fix-append-data-callback-missing-gil.md` で「案 A: GIL 取得を追加」「案 B: 廃止予定 API ごと削除」のどちらにするか未確定で pending 状態。本 issue で方針を確定する。

## 設計方針

`pending/0013` で示されている案 A・案 B のいずれかを採用する。実装時に以下のうちから選定する (本 issue では断定しない):

### 案 A: GIL 取得を追加

`AppendData` と `SoraAudioStreamSinkImpl::OnData` の `call_python` 呼び出し直前で `gil_scoped_acquire acq;` を取得する。`buffer_mtx_` を握ったまま GIL を取得することになるため、ロック順序を再点検し、GIL → mutex の順序を全コードパスで保つこと (`gil.h` の `GILMutexLock` 設計と整合させる)。あるいは video sink と同様に `PostTask` 経由でワーカースレッドに飛ばし、そこで GIL を取る。

### 案 B: 廃止予定 API を削除

`on_data_` / `on_format_` は `src/sora_audio_sink.h:66-72` で「廃止予定」と明記されている。`Read()` API が代替として整備されているため、`on_data_` / `on_format_` を削除する。`SoraAudioStreamSink` の `on_frame_` は廃止予定ではないため案 A で対応。

`CHANGES.md` の `## develop` セクションに `[FIX]` (案 A) または `[CHANGE]` (案 B) エントリを追加する。

## 完了条件

- `SoraAudioSinkImpl::AppendData` の `on_format_` / `on_data_` 呼び出しと `SoraAudioStreamSinkImpl::OnData` の `on_frame_` 呼び出しが、GIL を保持した状態で行われるか、廃止される。
- libwebrtc のオーディオワーカースレッドから Python オブジェクトを GIL 非保持で触る経路がコードベース全体で残っていないこと。
- `pending/0013-bug-fix-append-data-callback-missing-gil.md` を `issues/closed/` に移動 (本 issue が close されたタイミング)。
- 既存のオーディオテストが通り続けること (`tests/test_audio_sink_read_gil.py` ほか)。
- 案 B を採る場合は CHANGES.md の `[CHANGE]` エントリで後方互換破壊を明示する。
