# `SoraAudioSinkImpl` と `SoraAudioStreamSinkImpl` の音声コールバックで GIL を取得する

- Priority: High
- Created: 2026-06-23
- Polished: 2026-07-13
- Model: Opus 4.7
- Branch: feature/fix-audio-on-data-missing-gil

## 目的

libwebrtc の音声処理スレッドから呼ばれる音声コールバックで、Python の処理を開始する前に GIL を取得する。

対象は次の 3 経路である。

- `SoraAudioSinkImpl::AppendData` の `on_format_`
- `SoraAudioSinkImpl::AppendData` の `on_data_`
- `SoraAudioStreamSinkImpl::OnData` の `on_frame_`

現在は `call_python` が GIL を取得しないため、これらのコールバックを設定した場合、Python callable を保持する `std::function` の呼び出し、`nb::ndarray` の構築、Python オブジェクトの参照カウント操作が GIL 非保持で実行される。
これは Python C API の利用規約違反であり、参照カウント競合やヒープ破壊によるプロセスのクラッシュにつながる。

既存のコールバック API と同期的な呼び出し方は維持する。
廃止予定とコメントされている `on_data_` / `on_format_` も、今回の issue では削除しない。

## 優先度根拠

High とする。

- `on_data`、`on_format`、`on_frame` は現在も nanobind バインディングと `.pyi` で公開されている。
- コールバックを設定した利用者では、音声フレームを受信するたびに GIL 非保持の Python 呼び出し経路へ到達する。
- `SoraAudioStreamSink.on_frame` は VAD の実テスト (`tests/test_vad.py`) でも使用されており、廃止予定 API に限定された問題ではない。
- native レイヤの未定義動作は Python 例外として回復できず、正式リリース前に解消する必要がある。

## 現状

### `SoraAudioSinkImpl::AppendData`

`src/sora_audio_sink.cpp:103-136` の `AppendData` は、`SoraAudioSinkImpl::OnData` (`:52-101`) から呼ばれる。
`OnData` は `webrtc::AudioTrackSinkInterface::OnData` の実装で、関数内で GIL を取得していない。

現在の Python 呼び出し箇所は次のとおりである。

```cpp
// src/sora_audio_sink.cpp:107-117
{
  std::unique_lock<std::mutex> lock(buffer_mtx_);
  ...
  if (on_format_) {
    call_python(on_format_, sample_rate_, number_of_channels_);
  }
}
```

```cpp
// src/sora_audio_sink.cpp:129-135
if (on_data_) {
  size_t shape[2] = {number_of_frames, number_of_channels_};
  auto data = nb::ndarray<nb::numpy, int16_t, nb::shape<-1, -1>>(
      (void*)audio_data, 2, shape, nb::handle());
  call_python(on_data_, data);
}
```

`on_data_` の `nb::ndarray` 構築も Python C API に触れるため、`call_python` の直前だけでなく、`nb::ndarray` を構築する前から GIL を保持しなければならない。

`on_data` と `on_format` は `src/sora_sdk_ext.cpp:441-449` で公開され、型スタブにも `src/sora_sdk/sora_sdk_ext.pyi:111-128` で残っている。
ヘッダ (`src/sora_audio_sink.h:66-72`) には廃止予定と書かれているが、削除はまだ行われていない。

### `SoraAudioStreamSinkImpl::OnData`

`src/sora_audio_stream_sink.cpp:176-211` の `OnData` は同じ `webrtc::AudioTrackSinkInterface::OnData` 経由で呼ばれる。
`src/sora_audio_stream_sink.cpp:209-210` で `on_frame_` を直接呼び出しているが、呼び出し前に GIL を取得していない。

`on_frame_` は `src/sora_audio_stream_sink.h:184-192` でメインスレッドから呼ばれないと説明されており、`tests/test_vad.py:116-122` でも実際に設定されている。

### GIL とロックの現状

`src/sora_call.h:13-25` の `call_python` は例外をログへ出力して再送出するだけで、GIL を取得しない。
GIL の取得は各呼び出し側の責務である。

`SoraAudioSinkImpl::Read` は `src/sora_audio_sink.cpp:145` の `GILMutexLock` を使い、GIL を保持してから `buffer_mtx_` を取得する。
一方、現在の `AppendData` は `buffer_mtx_` を取得してから Python コールバックを呼ぶ構造である。
`src/dummy_audio_mixer.cpp:17-31` の `DummyAudioMixer::Mix` が mutex を保持したまま音声 source を処理し、音声 sink の `OnData` を発火させることも確認できる。

そのため、単に `on_format_` の呼び出し直前へ GIL 取得を追加してはならない。
少なくとも `Read` と共有する `buffer_mtx_` については、GIL → `buffer_mtx_` の順序を保つ必要がある。

### 参考実装との差分

`src/sora_video_sink.cpp:102-114` は、`OnFrame` で Python を直接呼ばず、タスクキュー上で GIL を取得してから `call_python` を呼ぶ。
これは映像側のロック制約を回避するための実装であり、音声側へそのまま適用できるとは限らない。
今回の音声修正では、`on_data` が `OnData` の引数バッファを参照する既存 API であること、および同期的な呼び出し方を維持することを前提に、呼び出し側で GIL を取得する。

## 設計方針

既存の 3 コールバックを削除せず、Python C API に触れる処理の開始前に GIL を取得する。

### `SoraAudioSinkImpl::AppendData`

`src/sora_audio_sink.cpp:103-136` の `AppendData` の先頭で `gil_scoped_acquire acq;` を構築し、そのスコープを `AppendData` の末尾まで維持する。
これにより、次の全てが GIL 保持下で実行される。

- `buffer_mtx_` の取得
- `on_format_` の有無確認と呼び出し
- `on_data_` の有無確認
- `nb::ndarray` の構築
- `on_data_` の呼び出し

`buffer_mtx_` を取得するコードより前に GIL を取得することが必須である。
`Read` の `GILMutexLock` と同じ GIL → `buffer_mtx_` の順序を維持し、`buffer_mtx_` → GIL の順序を新たに作らない。

`number_of_channels_` は `buffer_mtx_` 保持中にローカル変数へ snapshot し、mutex を解放した後の `nb::ndarray` の shape にはその snapshot を使う。

`on_data_` に渡す配列の shape、dtype、入力バッファの所有権、コールバックの同期的な呼び出し方は変更しない。
`on_data_` の配列をコールバックの外へ保持できないという既存の制約も変更しない。

### `SoraAudioStreamSinkImpl::OnData`

`src/sora_audio_stream_sink.cpp:209-210` の `on_frame_` 呼び出し前に `gil_scoped_acquire acq;` を構築する。
GIL の取得後に `on_frame_` を読み出し、`SoraAudioFrame` の Python コールバック引数を構築して `call_python` を呼ぶ。`on_frame_` が未設定の場合の既存の例外挙動は変更しない。

音声データの整形処理 (`webrtc::AudioFrame` の生成、リサンプリング、チャンネル変換) は Python C API に触れないため、GIL 取得前に実行してよい。
ただし、`on_frame_` の読み出し、`std::make_shared<SoraAudioFrame>`、`call_python` は GIL 保持スコープ内に置く。

### ロック順序と終了処理

- `SoraAudioSinkImpl::Read` と `AppendData` の `buffer_mtx_` 取得順序を GIL → mutex に統一する。
- `DummyAudioMixer::Mix` が mutex 保持中に音声 callback を発火する経路を確認し、今回追加する GIL → `buffer_mtx_` の順序による `Read` との相互待ちを発生させないこと。callback 自身からの同期的な `Read` 呼び出しや sink 破棄は既存の再入制約があるため、今回の回帰テストの対象にしない。
- `gil_scoped_acquire` は既存の `src/gil.h` の実装を使用し、GIL の取得処理を `call_python` へ移動しない。
- `SoraAudioSinkImpl` と `SoraAudioStreamSinkImpl` のデストラクタ、`Disposed`、`PublisherDisposed` の呼び出し順序は変更しない。

### 変更対象

- `src/sora_audio_sink.cpp`: `AppendData` の GIL 取得とロック順序の修正。
- `src/sora_audio_stream_sink.cpp`: `gil.h` の include と、`OnData` の `on_frame_` 呼び出し前の GIL 取得。
- `tests/test_audio_sink_callbacks.py` (新規): `on_format` / `on_data` の実接続テスト。
- `tests/test_vad.py`: `_on_frame` で `Event` を設定し、テスト本体で timeout 付きの `Event.wait()` をアサートして、`SoraAudioStreamSink.on_frame` の実接続 callback 発火を検証する。
- `CHANGES.md`: `## develop` に `[FIX]` エントリを追加する。

`src/sora_sdk_ext.cpp`、`src/sora_sdk/sora_sdk_ext.pyi`、公開 API のシグネチャは変更しない。

### テスト方針

モックやスタブは使用せず、既存の実接続テスト環境を利用する。

`tests/test_audio_sink_callbacks.py` は `tests/client.py` の `SoraClient` を使い、次の構成にする。

1. `SENDONLY` クライアントを `fake_audio=True` で接続する。
2. `RECVONLY` クライアントを接続し、独自の `on_track` で `SoraAudioSink` を生成する。
3. `on_track` の中で音声データの到着前に `on_format` と `on_data` を設定する。sink 生成後にポーリングして設定するだけでは、最初のフォーマット通知を取り逃がすため禁止する。
4. 各コールバック内で、イベント設定、Python のリスト更新、NumPy 配列の shape / dtype 確認を行う。
5. timeout 付きで両コールバックの発火を待ち、`on_format` がサンプリングレートとチャネル数を受け取り、`on_data` が `int16` の 2 次元配列を受け取ったことを確認する。
6. コールバックがメインスレッド以外から実行されたことを確認し、切断前にイベント待機中の処理を終了する。

`tests/test_vad.py` では `_on_frame` 内で `Event` を設定し、テスト本体で timeout 付きの `Event.wait()` をアサートする。
コールバックで `SoraVAD.analyze(frame)` を実行する既存経路が成功し、接続終了時に callback 発火待ちが残らないことを確認する。

GIL の保持状態そのものは Python の callback だけでは判定できないため、テストは「GIL 非保持での Python 呼び出しがクラッシュしないこと」と「対象経路が実際に発火すること」を検証し、GIL 取得の有無は C++ の実装確認で担保する。

次の並行性も確認する。

- `read()` の待機中に別スレッドから音声 callback が発火しても、既存の `tests/test_audio_sink_read_gil.py` が通ること。
- callback が未設定の場合に、既存の `Read` の戻り値、タイムアウト、音声データの shape が変わらないこと。

callback 例外のログ出力と送出挙動は `src/sora_call.h:13-25` のコード確認で担保する。
native 音声スレッド上で例外を実際に送出させる E2E テストは、未処理例外によるプロセス終了を招くため追加しない。

## 完了条件

- `SoraAudioSinkImpl::AppendData` の `on_format_`、`on_data_` と `nb::ndarray` 構築が GIL 保持下で実行されること。
- `SoraAudioStreamSinkImpl::OnData` の `on_frame_` の読み出し、引数構築、Python callback 呼び出しが GIL 保持下で実行されること。`on_frame_` 未設定時の既存の例外挙動を変更しないこと。
- `AppendData` と `Read` の `buffer_mtx_` 取得順序が GIL → mutex で統一され、既存の待機処理にデッドロックを導入しないこと。
- `DummyAudioMixer::Mix` が mutex 保持中に音声 callback を発火する経路を含め、今回追加する GIL → `buffer_mtx_` の順序による `Read` との相互待ちを発生させないこと。
- `on_data`、`on_format`、`on_frame` の公開 API、同期的な呼び出し方、引数の型と shape が変わらないこと。
- `tests/test_audio_sink_callbacks.py` で `on_format` と `on_data` の実接続 callback 発火を検証すること。
- `tests/test_vad.py` で `SoraAudioStreamSink.on_frame` の実接続 callback 経路が成功すること。
- 既存のオーディオテストと全体のビルド・テストが通ること。
- `CHANGES.md` の `## develop` に、担当者行付きの `[FIX]` エントリを追加すること。
- 実装と同じ変更で対象範囲を引き継いだ `issues/pending/0013-bug-fix-append-data-callback-missing-gil.md` を `issues/closed/` へ移動し、重複して open / pending のまま残さないこと。

## 後方互換性

Python 公開 API は削除・改名せず、`on_data`、`on_format`、`on_frame` の引数型・戻り値・同期的な callback 呼び出しを維持する。
変更されるのは、libwebrtc の音声スレッドから Python callback を実行する前に GIL を取得する点だけである。

## 関連 issue

- `issues/pending/0013-bug-fix-append-data-callback-missing-gil.md`: `SoraAudioSinkImpl::AppendData` の `on_format_` / `on_data_` を対象にした pending issue。0018 が対象範囲を引き継ぎ、`SoraAudioStreamSinkImpl::OnData` も含めて扱う。
- `issues/0019-bug-fix-frame-transformer-missing-gil.md`: frame transformer の別の GIL 未取得問題。対象シンボルは重複しない。
- `issues/closed/0009-bug-fix-on-push-missing-gil.md`: GIL 非保持で Python callback を呼ぶ問題を修正した先例。
- `issues/closed/0012-bug-fix-audio-sink-read-holds-gil.md`: `Read` の GIL 解放と `GILMutexLock` 導入の先例。
- `issues/closed/0014-bug-fix-read-pyerr-checksignals-not-propagated.md`: `Read` の Python 例外伝播を修正した先例。
- `issues/0055-refactor-sora-connection-callbacks-private.md`: 廃止予定の `on_data_` / `on_format_` を当面維持し、次のメジャーで除去する方針。0018 ではこの API 方針を変更しない。
- `issues/0057-bug-fix-gil-scope-uninitialized-member.md`: `gil_scoped_acquire` の終了処理時の未初期化メンバを扱う別 issue。0018 では `src/gil.h` を変更しない。
