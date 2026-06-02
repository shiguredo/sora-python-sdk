# SoraAudioSinkImpl::Read が待機中に GIL を保持し続ける問題を修正する

- Priority: Medium
- Created: 2026-06-02
- Model: Opus 4.8
- Branch: feature/fix-audio-sink-read-holds-gil

## 目的

`SoraAudioSink.read()` は内部で `SoraAudioSinkImpl::Read`
(`src/sora_audio_sink.cpp:137`) を呼び、指定フレーム数が貯まるまで
`std::condition_variable::wait_for` で待機する。この待機中、`Read` は GIL
(Python のグローバルインタプリタロック) を一切解放しない。

その結果、`read(timeout=T)` を呼んだスレッドは、データが届かなければ最大 T 秒
間 GIL を握ったままブロックする。GIL は同一プロセスで同時に一つのスレッドし
か保持できないため、その間、同一プロセス内の他の Python 実行 (別接続のシグナ
リング処理、コールバック、ユーザーが同居させている HTTP サーバ等) が T 秒間
すべて停止する。

本 issue はこの待機中の GIL 保持を解消し、`Read` のブロック中も他の Python ス
レッドが進行できるようにする。

## 優先度根拠

Medium とする。

- `read()` を `timeout` 付きで呼び、かつ同一プロセスで他の Python 処理を並行さ
  せている構成では、データ未達のたびに最大 `timeout` 秒の全 Python 停止が確定
  的に発生する。とりわけ複数接続を 1 プロセスに同居させる構成や、`read` と同
  居する in-process のサーバ・タイマーを持つ構成で顕在化する。
- クラッシュではなく「他スレッドの遅延・飢餓」として現れるため致命度は High に
  満たないが、`read()` は本 SDK の音声取得の主要 API であり、影響範囲は広い。
- 本件の発見契機は E2E テストの flaky 化である。`read(timeout=5)` の待機中に同
  一プロセスのシグナリング (別接続の re-answer 生成) が GIL 待ちで進まず、その
  接続の音声が `read` のタイムアウトに連動して遅延し、結果として `read` 自体も
  失敗する、という連鎖が観測された。`timeout` を伸ばすと GIL 保持時間も伸び、
  飢餓が悪化するため、`timeout` 調整では解決しない。
- 修正は本 SDK 内の `Read` 実装に閉じ、API・シグネチャ・挙動 (戻り値) は不変。
  同種の GIL 解放パターンは本リポジトリに既存実装がある (後述) ため、リグレッ
  ションリスクは低い。

## 現状

### 根本原因

`SoraAudioSinkImpl::Read` は `buffer_mtx_` を `std::unique_lock` で取得した
まま、`std::condition_variable::wait_for` で待機する
(`src/sora_audio_sink.cpp:137-155`)。

```cpp
nb::tuple SoraAudioSinkImpl::Read(size_t frames, float timeout) {
  std::unique_lock<std::mutex> lock(buffer_mtx_);

  size_t num_of_samples;
  if (frames > 0) {
    // フレーム数のリクエストがある場合はリクエスト分が貯まるまで待つ
    if (!buffer_cond_.wait_for(
            lock,
            std::chrono::nanoseconds(/* timeout 換算 */),
            [&] {
              return (number_of_channels_ > 0 &&
                      buffer_.size() >= frames * number_of_channels_) ||
                     PyErr_CheckSignals() != 0;
            })) {
      return nb::make_tuple(false, nb::none());
    }
    ...
```

- `Read` は Python から呼ばれる関数なので、入口では GIL を保持している。
  `wait_for` の前後で GIL を解放する処理が無いため、待機中もずっと GIL を保持し
  続ける。
- predicate が `PyErr_CheckSignals()` を呼んでいる。これは GIL 保持が前提の
  Python C API であり、「Ctrl-C 等のシグナルで待機を中断できるようにする」ため
  に置かれている。単純に `wait_for` の手前で GIL を解放すると、この predicate
  が GIL 非保持で Python C API を呼ぶことになり、別の未定義動作を招く。した
  がって「待機中だけ GIL を解放し、predicate 評価時に GIL を取り直す」必要が
  ある。
- `buffer_cond_` は `std::condition_variable` 型 (`src/sora_audio_sink.h`) で、
  GIL を mutex として直接扱えない。

待機中に GIL を保持したままだと、同一プロセスで GIL を必要とする他のすべての
Python スレッドは、`Read` がデータ到着・タイムアウト・シグナルのいずれかで
`wait_for` を抜けて GIL を手放すまで進めない。`read(timeout=T)` がタイムアウト
で抜ける最悪ケースでは、これが最大 T 秒間継続する。

### 本リポジトリに既存の正解パターン

本リポジトリには「condition variable の待機中に GIL を解放し、再取得時に
GIL を取り直す」ための仕組みが既にある。

- `src/gil.h` の `GILLock`: `lock()` で `PyEval_RestoreThread` (GIL 取得)、
  `unlock()` で `PyEval_SaveThread` (GIL 解放) を行う、`BasicLockable` 準拠の
  アダプタ。`std::condition_variable_any` の待機対象として使うと、待機の前後で
  自動的に GIL を解放・再取得できる。`Py_Finalize` 中の起床も考慮済み。
- `src/sora_video_source.cpp:64-66` が実例。`std::condition_variable_any`
  (`src/sora_video_source.h:103` の `queue_cond_`) を `GILLock` で待つことで、
  フレーム待機中に GIL を解放している。

`SoraAudioSinkImpl::Read` はこのパターンを踏襲していない (待機対象が
`std::mutex` + `std::condition_variable` のまま) のが現状の差分である。

### 利用側で回避できるか

回避できない。GIL の保持・解放は `Read` の C++ 実装に属し、`read()` の呼び出し
側から制御する API は無い。利用側は `frames` と `timeout` を渡せるだけで、待機
中に GIL を握り続けるか否かには関与できない。`read` を専用プロセスに隔離すれば
他の Python 処理への影響は避けられるが、それは API としての回避策ではなく構成上
の制約の押し付けである。

## 設計方針

`Read` の待機を `GILLock` + `std::condition_variable_any` 化し、`wait_for` の
待機中だけ GIL を解放する。`src/sora_video_source.cpp` の既存パターンに揃える。

- `src/sora_audio_sink.h` の `buffer_cond_` を
  `std::condition_variable` から `std::condition_variable_any` に変更する。
  `AppendData` 側の `notify_all` (`src/sora_audio_sink.cpp:125`) は型に依らず
  同じ呼び出しで動く。
- `Read` 内の待機を、`buffer_mtx_` ではなく `GILLock` を介して待つ形にする。
  これにより `wait_for` がスレッドをブロックして待つ間は GIL が解放され、
  起床して predicate を評価する瞬間には GIL が取得済みになる。
  predicate 内の `PyErr_CheckSignals()` は GIL 保持下で評価されるため、シグナル
  による中断という既存の挙動はそのまま維持される。
- バッファ (`buffer_`)・フォーマット (`number_of_channels_` 等) を共有保護して
  いる `buffer_mtx_` と、GIL の二つのロック関係を破綻させないこと。
  `AppendData` は `buffer_mtx_` を取得して `buffer_` を更新し `notify_all` する。
  `Read` がバッファを読む区間 (`src/sora_audio_sink.cpp:171-185`) は引き続き
  `buffer_mtx_` による排他が必要である。待機の GIL 解放化にあたり、この
  バッファ保護が緩まないよう実装すること (具体的な lock 構成は実装時に確定する。
  GIL 解放と `buffer_mtx_` 解放の順序、起床後のバッファ再確認を含めて、データ
  競合と取りこぼしが起きないことを確認する)。
- `frames == 0` の分岐 (`src/sora_audio_sink.cpp:163-169`) は待機しないので、
  GIL 保持の問題は無い。ただし `buffer_` へアクセスするため `buffer_mtx_` に
  よる排他は維持する。
- Python から見える `read()` の API・シグネチャ・戻り値・タイムアウト挙動・
  シグナル中断挙動はいずれも変えない。後方互換性に影響はない。
- 本リポジトリ単独で完結する。外部依存の変更は不要。

### 同種の確認対象

同じ「待機中 GIL 保持」が `src/sora_audio_stream_sink.cpp` 等の他の sink にも
無いかを併せて確認する。`Read` 相当の待機 API を持ち同じ問題を抱えるものがあれ
ば、本 issue の対象に含めるか別 issue として切り出すかを判断する (まずは本 issue
で `SoraAudioSinkImpl::Read` を確実に直すことを優先する)。

### テスト方針

本バグは「`read()` 待機中の GIL 保持」であり、メディアが流れる必要は無い。
バッファが空のまま `wait_for` がブロックするだけで確定的に再現するため、レース
を踏ませる必要がなく、**決定的 (非 flaky) なテスト**にできる。以下の構成で
`tests/` に再現テストを追加する。

#### 前提: sink は単体生成できない (実接続が必要)

`SoraAudioSink` のコンストラクタは `track` (`SoraTrackInterface`) を要求し
(`src/sora_sdk_ext.cpp:443`、`src/sora_sdk/__init__.py:34`)、この track は接続の
`on_track` コールバック経由でしか得られない。track を単体生成する公開 API は
無いため、sink を単体で作ることはできず、実 Sora 接続を 1 本張る必要がある。
`tests/` は元々実サーバ前提 (`tests/conftest.py` の `TEST_SIGNALING_URLS` 等)
で、`tests/client.py` の `_on_track` (`:500-507`) が audio track から
`SoraAudioSink` を生成する既存ハーネスをそのまま流用できる
(`tests/test_sendonly_recvonly.py` 等が同型)。

#### 再現テストの構成

1. 既存ハーネスで接続を張り、`on_track` 経由で audio sink を 1 個得る。
2. 別スレッドで、タイムアウト内に絶対に満たされない大きな `frames` を指定して
   `sink.read(frames=<巨大>, timeout=T)` を呼ぶ。バッファが空のまま `wait_for`
   が T 秒ブロックすることを保証する。
3. メインスレッドで軽い Python 処理をループしてハートビートカウンタを進め、その
   T 秒間にカウンタがどれだけ進んだかを計測する。
4. アサート: その T 秒間にメインスレッドが進んだこと (カウンタが十分に増えた
   こと)。
   - 修正前: `Read` が C レベルで GIL を握ったまま `wait_for` するため CPython
     の GIL 切り替えが起きず、メインスレッドは T 秒間飢餓してカウンタがほぼ
     進まない → fail。
   - 修正後: 待機中に GIL が解放され、メインスレッドが進む → pass。
   - しきい値は余裕を持たせる (例: T 秒間にカウンタが N 回以上進むこと)。GIL
     保持の有無で進捗が「ほぼ 0」対「多数」と明確に分かれるため、環境差で誤判定
     しにくい。

- モックやスタブは使わない (CLAUDE.md)。実接続・実 sink・実スレッドで再現する。
- シグナル中断 (`PyErr_CheckSignals`) の挙動が維持されることも確認する。

## 完了条件

- `SoraAudioSinkImpl::Read` の待機 (`wait_for`) 中に GIL が解放され、起床後の
  predicate 評価時には GIL が取得済みであること (`src/gil.h` の `GILLock` と
  `std::condition_variable_any` を用いる)。
- `read()` の API・戻り値・タイムアウト挙動・シグナル中断挙動が従来どおりである
  こと。
- `buffer_mtx_` によるバッファ・フォーマットの排他保護が緩んでおらず、
  `AppendData` と `Read` の間でデータ競合・取りこぼしが無いこと。
- ビルドが通り、既存テストが全て通ること。
- 「`read(timeout=T)` の待機中にメインスレッドの Python が進める」ことを検証する
  決定的な再現テストを `tests/` に追加していること (「テスト方針」の構成)。修正前
  は fail し、修正後は pass することを確認していること。
- `CHANGES.md` の `## develop` に `[FIX]` エントリを担当者行付きで追記している
  こと (CLAUDE.md の種別順・書式に従う)。

## 解決方法

(対応後に記載する)
