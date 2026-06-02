# SoraAudioSinkImpl::Read が待機中に GIL を保持し続ける問題を修正する

- Priority: Medium
- Created: 2026-06-02
- Polished: 2026-06-02
- Model: Opus 4.8
- Branch: feature/fix-audio-sink-read-holds-gil

## 目的

`SoraAudioSink.read()` は内部で `SoraAudioSinkImpl::Read`
(`src/sora_audio_sink.cpp:137`) を呼び、指定フレーム数が貯まるまで
`std::condition_variable::wait_for` で待機する。この待機を `buffer_mtx_` を握った
まま行い、かつ GIL (Python のグローバルインタプリタロック) を解放しない。

その結果、`read(timeout=T)` を呼んだスレッドは、データが指定フレーム数に達しなけ
れば最大 T 秒間 GIL を握ったままブロックする。GIL は同一プロセスで同時に一つの
スレッドしか保持できないため、その間、同一プロセス内の他のすべての Python 実行
(別接続のシグナリング処理、コールバック、ユーザーが同居させている HTTP サーバ等)
が停止する。

本 issue はこの待機中の GIL 保持を解消し、`Read` のブロック中も他の Python ス
レッドが進行できるようにする。

## 優先度根拠

Medium とする。

- `read()` を `timeout` 付きで呼び、同一プロセスで他の Python 処理を並行させてい
  る構成では、データ未達のたびに最大 `timeout` 秒の全 Python 停止が確定的に発生
  する。とりわけ複数接続を 1 プロセスに同居させる構成や、`read` と同居する
  in-process のサーバ・タイマーを持つ構成で顕在化する。
- `read()` は本 SDK の音声取得の主要 API であり影響範囲は広い。発見契機は E2E
  テストの flaky 化で、`read` の待機中に同一プロセスのシグナリング (別接続の
  re-answer 生成) が GIL 待ちで進まず、その接続の音声が `read` のタイムアウトに
  連動して遅延し、`read` 自体も失敗する連鎖が観測された。`timeout` を伸ばすと
  GIL 保持時間も伸びて飢餓が悪化するため、`timeout` 調整では解決しない。
- High としない理由: プロセスのクラッシュやメモリ破壊ではなく、他スレッドの遅延
  ・飢餓に留まる (機能不全ではあるが回復可能)。修正は本 SDK 内の `Read` 実装に
  閉じ、API・シグネチャ・挙動 (戻り値) は不変で、リグレッションリスクは限定的。

## 現状

### 根本原因

`SoraAudioSinkImpl::Read` は `buffer_mtx_` を `std::unique_lock` で取得した
まま `std::condition_variable::wait_for` で待機するが
(`src/sora_audio_sink.cpp:137-155`)、待機の前後で GIL を解放しない。`Read` は
Python から GIL を保持して入場するため、待機中もずっと GIL を握り続ける。待機を
抜ける契機 (データ到着・タイムアウト・シグナル) まで他の Python スレッドは進めず、
`read(timeout=T)` がタイムアウトで抜ける最悪ケースではこれが最大 T 秒継続する。

### 並行モデル: producer は GIL 非保持の WebRTC スレッド

この修正の難所は、`buffer_` の producer と consumer で GIL の保持状況が異なる点
にある。

- consumer (`Read`): Python から呼ばれ GIL を保持して入場する。
- producer (`OnData` → `AppendData`, `src/sora_audio_sink.cpp:51-135`):
  `webrtc::AudioTrackSinkInterface::OnData` のコールバックで、**GIL を保持しない
  WebRTC オーディオスレッド**から呼ばれる。そのため `buffer_` /
  `number_of_channels_` は GIL ではなく `buffer_mtx_` で保護されている
  (`AppendData` は `buffer_mtx_` を取得して `buffer_` を更新し
  `buffer_cond_.notify_all()` する, `:106-126`)。

したがって `Read` の predicate (`:148-151`) は `PyErr_CheckSignals()` (GIL が必要)
と `buffer_.size()` / `number_of_channels_` (`buffer_mtx_` が必要) を同一式で評価
する。**predicate 評価時には GIL と `buffer_mtx_` の両方が必要**である。

なお `src/sora_video_source.cpp:63-79` も待機中に `GILLock` で GIL を解放するが、
そこは producer (`OnCaptured`) も Python (GIL 保持) から呼ばれ、共有データを GIL
だけで保護している。本件は producer が GIL 非保持の WebRTC スレッドであるため
GIL をデータロックに使えず、`GILLock` だけで待つ単純パターンは流用できない。
GIL と `buffer_mtx_` の二つのロックを協調させる必要がある。

## 設計方針

`buffer_cond_` を `std::condition_variable_any` 化し、待機中に GIL と
`buffer_mtx_` の両方を解放・再取得する「合成ロック」を `wait_for` に渡す。

### 具体構成

1. `src/sora_audio_sink.h:95` の `buffer_cond_` を `std::condition_variable` から
   `std::condition_variable_any` に変更する。`AppendData` 側の `notify_all`
   (`src/sora_audio_sink.cpp:125`) は型に依らず同じ呼び出しで動く。
2. GIL と `buffer_mtx_` を束ねる `BasicLockable` 準拠の合成ロックを用意する。GIL
   側は `src/gil.h` の `GILLock` をメンバとして内包して再利用する (`GILLock` の
   初期状態 `state_ == nullptr` は「GIL 保持中」を意味し、GIL 保持で入場する
   `Read` と整合するため追加初期化は不要)。合成ロックは `GILLock` の終了処理中
   (`Py_IsInitialized() == false`) の挙動をそのまま引き継ぐ (`sora_video_source.cpp`
   等で既に使われている `GILLock` と同じ挙動)。設置場所は `gil.h` あるいは
   `sora_audio_sink` 近傍とする。
   - `lock()`: GIL 取得 → `buffer_mtx_` ロック
   - `unlock()`: `buffer_mtx_` アンロック → GIL 解放
3. `condition_variable_any::wait_for(合成ロック, timeout, predicate)` により、
   ブロック中は合成ロックが `unlock()` され GIL と `buffer_mtx_` が両方解放される
   (他の Python スレッドが進行でき、WebRTC スレッドの `AppendData` も
   `buffer_mtx_` を取得して append できる)。起床して predicate を評価する瞬間には
   `lock()` 済みで両方を保持し、`PyErr_CheckSignals()` は GIL 下、`buffer_.size()`
   は `buffer_mtx_` 下で安全に評価される (シグナル中断の既存挙動も維持される)。

### GIL を解放する範囲は待機中のみ

`Read` は GIL 保持で入場し、GIL を解放するのは `wait_for` のブロック中だけであ
る。待機後のバッファ読み出し区間 (`:171-185`) は `nb::ndarray` / `nb::capsule` の
構築という Python C API を含むため GIL 必須であり、ここと `frames == 0` 分岐
(`:163-169`) は GIL を保持したまま (`buffer_mtx_` も保持して) 実行する。実装時に
「全経路で GIL を解放する」と誤って読み出し区間の GIL を落とさないこと。

### ロック順序

`Read` のロック順序は GIL → `buffer_mtx_`、解放は逆順になる。`condition_variable_any`
は notify 時も起床時も内部 mutex を保持したまま `buffer_mtx_` / GIL を取りに行か
ない (`notify_all` は内部 mutex を取得即解放してから通知し、起床時は内部 mutex を
解放してから合成ロックを再取得する) ため、`buffer_mtx_` ・ GIL ・内部 mutex の
3 者間に循環待ちは生じない。`AppendData` も通常パスで GIL に触れないため GIL が
からむ反転は無い。

例外として `AppendData` は `buffer_mtx_` 保持中に `call_python(on_format_, ...)`
(`:115`) を呼ぶ経路があるが、`on_format_` / `on_data_` はヘッダに「廃止予定」と
明記され既定で未設定であり、本 issue のスコープ外とする (この経路が抱える GIL
非保持の Python C API 呼び出しは別途扱う)。

### 他の sink はスコープ外 (確認済み)

GIL を保持したままブロックする待機 API は、`src/` 全体で
`SoraAudioSinkImpl::Read` のみである (`wait_for` / `condition_variable` を全
`src/` で確認)。`src/sora_audio_stream_sink.cpp` はコールバック駆動で待機 API を
持たず、`src/sora_video_source.cpp` / `src/sora_connection.cpp` の待機は既に
`GILLock` + `std::condition_variable_any` で GIL を解放している。よって本 issue
の対象は `SoraAudioSinkImpl::Read` に閉じる。

### 後方互換

Python から見える `read()` の API・シグネチャ・戻り値・タイムアウト挙動・シグナル
中断挙動はいずれも変えない。`src/sora_sdk_ext.cpp:446` のバインドも変更不要。
外部依存の変更も不要で、本リポジトリ単独で完結する。

## テスト方針

producer がメディアを流していても、`read` が要求する `frames` を満たさない限り
`wait_for` がブロックして GIL を握り続けるため、**決定的 (非 flaky) なテスト**に
できる。レースを踏ませる必要はない。

### 前提: sink は単体生成できず 2 接続構成が必要

`SoraAudioSink` のコンストラクタは `track` (`SoraTrackInterface`) を要求し
(`src/sora_sdk_ext.cpp:443`、`src/sora_sdk/__init__.py:34`)、track はリモートの
`on_track` 経由でしか得られない。recvonly 単独では送信相手がいないので track が
来ない。よって `tests/test_sendonly_recvonly.py` と同型の 2 接続構成を用いる。

- sendonly クライアントを `fake_audio=True` で接続して音声を流す
  (`tests/client.py` の `connect(fake_audio=True)`, `:237`)。
- 別途 recvonly クライアントを接続し、その `_on_track` (`tests/client.py:500-507`)
  で `self._audio_sink` に `SoraAudioSink` が生成される。recvonly の出力サンプリン
  グレートは `tests/client.py` の既定 16000 Hz・1 ch (`:68-69`)。

`_audio_sink` は private 属性で読み出しヘルパが無いため、テストからは
`recvonly._audio_sink` を直接参照する。`on_track` は非同期で呼ばれるので、
`recvonly._audio_sink is not None` になるまで timeout 付きでポーリングして待つ。

### 再現テストの構成

1. 上記 2 接続を確立し、recvonly 側の `_audio_sink` を取得する。
2. 別スレッドで、タイムアウト内に満たされない大きな `frames` を指定して
   `sink.read(frames=16000 * 3600, timeout=T)` を呼ぶ (既定 16000 Hz では 1 時間分
   で、T 秒では到達せず `wait_for` が T 秒ブロックする)。T は例えば 2 秒。
3. メインスレッドでハートビートを計測する。例: `while 経過 < T: counter += 1;
   time.sleep(0.01)`。`read` が GIL を握っている間はメインスレッドが `time.sleep`
   から復帰しても GIL 再取得待ちで進めず `counter` が伸びない。
4. アサート: T 秒間に `counter` が十分進んだこと。修正前は `read` スレッドが GIL
   を握ったまま `wait_for` するためメインスレッドが飢餓し `counter` がほぼ伸びず
   fail、修正後は待機中に GIL が解放され進むので pass。閾値は余裕を持たせる
   (T=2 秒・interval=0.01 秒なら理想は約 200。例えば `counter > 50` を pass 条件に
   すれば GIL 保持の有無で「ほぼ 0」対「100 超」と明確に分かれ、環境差で誤判定し
   にくい)。
5. 後始末: `read` スレッドは T 秒で自然に返るので、メインスレッドで
   `read_thread.join(timeout=T + α)` してから両クライアントを disconnect する
   (read がブロック中に disconnect すると sink 破棄と read スレッドが競合するため、
   join を先に行う)。

補足:

- モックやスタブは使わない (CLAUDE.md)。実接続・実 sink・実スレッドで再現する。
- 「修正前は fail」を同一ブランチで確認する手順: `buffer_cond_` の型変更を含む
  `src/sora_audio_sink.{h,cpp}` の修正は再ビルドが必要なため、テスト追加コミット
  と修正コミットを分け、テスト追加コミット (修正前) の時点でビルド・テストして
  fail を記録し、続く修正コミットで pass を確認する。
- シグナル中断 (`PyErr_CheckSignals`) の挙動維持は、Python テストから決定的に
  シグナルを踏ませるのが難しいため、自動テストではなくコードレビューで確認する。

## 完了条件

- `SoraAudioSinkImpl::Read` の待機中に GIL が解放され、他の Python スレッドが進行
  できること (上記再現テストで確認)。
- `read()` の API・戻り値・タイムアウト挙動・シグナル中断挙動が従来どおりである
  こと。
- `AppendData` と `Read` の間で `buffer_` のデータ競合・取りこぼし・デッドロックが
  無いこと。読み出し区間と `frames == 0` 分岐の GIL 保持が維持されていること。
- ビルドが通り、既存テストが全て通ること。
- 「`read(timeout=T)` の待機中にメインスレッドの Python が進める」ことを検証する
  決定的な再現テストを `tests/` に追加し、修正前は fail・修正後は pass することを
  確認していること。
- `CHANGES.md` の `## develop` に `[FIX]` エントリを担当者行付きで追記している
  こと (CLAUDE.md の種別順・書式に従う)。

## 解決方法

(対応後に記載する)
