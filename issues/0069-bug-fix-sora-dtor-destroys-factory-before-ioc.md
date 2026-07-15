# `Sora::~Sora` が factory を io_context より先に破棄するため GC のタイミング次第で SIGSEGV する問題を修正する

- Priority: High
- Created: 2026-07-16
- Model: Fable 5
- Branch: feature/fix-sora-dtor-destroys-factory-before-ioc

## 目的

e2e テスト（特に `tests/test_audio_sink_callbacks.py::test_audio_sink_callbacks`）が CI 上で flaky に SIGSEGV でクラッシュする問題の根本原因を修正する。クラッシュは 2026-07-13 の CI 実行以降、複数プラットフォーム（ubuntu-22.04/24.04 x86_64/arm64、macos-15、windows-2025）で繰り返し観測されており、`test_openh264_simulcast` や `test_sora_disconnect` など無関係なテストの実行中に「Garbage-collecting」中の abort として発生するケースもあった。

## 優先度根拠

High とする。

- プロセス全体が SIGSEGV / SIGABRT で落ちるメモリ安全性のバグであり、Python 例外として回復できない。
- CI の e2e テストがマージのたびに flaky に落ち、開発フローを阻害していた。
- 発生条件が「GC がいつ `SoraConnection` / `Sora` のサイクルを回収するか」というタイミング依存のため、ユーザーの本番コードでも接続の破棄後に任意のタイミングで発生しうる。

## 現状

`Sora::~Sora` の破棄順序が以下のようになっていた。

```cpp
Sora::~Sora() {
  factory_.reset();      // 1. PeerConnectionFactory (signaling/worker スレッドごと) を破棄
  if (thread_) {
    ioc_->stop();        // 2. io_context を停止
    thread_->join();
    thread_ = nullptr;
    ioc_ = nullptr;      // 3. io_context を破棄 (キューに残った handler は abandoned として破棄)
  }
  Disposed();
}
```

問題は手順 3 にある。`SoraConnection::Disconnect` が完了した後も、io_context のキューには `sora::SoraSignaling::DoInternalDisconnect` のタイマー handler などが `std::shared_ptr<sora::SoraSignaling>` を握ったまま残っていることがある。io_context の破棄時（`boost::asio::detail::scheduler::abandon_operations`）にこの handler が破棄されると、最後の `shared_ptr` が切れて `~SoraSignaling` が走る。`~SoraSignaling` はメンバの `SoraSignalingConfig::pc_factory`（`PeerConnectionFactoryProxy` への `scoped_refptr`）を解放し、プロキシのデストラクタは `webrtc::MethodCall::Marshal` で **手順 1 で既に破棄済みの signaling スレッド** に破棄処理を投げようとして use-after-free になり、SIGSEGV する。

### 再現手順

CI と同等の低速環境を作ると再現する。Apple Silicon の macOS では E コア限定で並列実行すると再現した。

```bash
for i in $(seq 1 25); do
  taskpolicy -b .venv/bin/python -m pytest tests/test_audio_sink_callbacks.py -q -p no:cacheprovider
done
```

これを 4 並列で実行すると、およそ 100 回中数回の頻度でテスト成功後のインタプリタ終了処理（GC が `SoraClient` ↔ `SoraConnection` の参照サイクルを回収するタイミング）で SIGSEGV する。lldb 配下で実行して取得したバックトレースは以下の連鎖を示す。

```
gc_collect_main
→ inst_dealloc(SoraConnection) → SoraConnection::~SoraConnection
→ publisher_->RemoveSubscriber(this) → intrusive_counter::dec_ref → Py_DECREF(Sora)
→ inst_dealloc(Sora) → Sora::~Sora → ioc_ = nullptr
→ kqueue_reactor::shutdown → abandon_operations
→ (DoInternalDisconnect のタイマー handler の破棄)
→ ~SoraSignaling → ~SoraSignalingConfig → ~scoped_refptr<PeerConnectionFactoryInterface>
→ ~RefCountedObject<PeerConnectionFactoryProxy> → MethodCall::Marshal(破棄済みスレッド) → EXC_BAD_ACCESS
```

CI ではテスト本体の実行中に後追いの GC が同じ経路を踏むため、「無関係なテストの実行中に worker プロセスが crash する」「faulthandler のダンプに `Garbage-collecting` が現れる」という形で観測されていた。

## 設計方針

破棄順序を「factory を参照しうるものを先に、factory を最後に」へ改める。

1. `Disposed()` で子（`SoraConnection` や各種 source）に破棄を通知する。
2. io_context を停止・破棄する。この時点で abandoned handler 経由の `~SoraSignaling` が走っても、factory とその signaling スレッドはまだ生きているため `Marshal` は正常に完了する。
3. 最後に `factory_` を破棄する。

また、io スレッドの handler や signaling スレッドのタスクは GIL を取得することがあるため、GIL を保持したまま `thread_->join()` や `Marshal` の完了を待つと相互待ちになりうる。スレッドの終了とネイティブリソースの破棄の間は GIL を解放する。

GIL 解放には `src/gil.h` の `gil_scoped_release` を使うが、同クラスには `Py_IsInitialized()` が偽のときに未初期化メンバをデストラクタで読む未定義動作があったため、前提条件として合わせて修正する（別 issue として管理）。

## 完了条件

- `Sora::~Sora` の破棄順序が「子への破棄通知 → io_context の停止・破棄 → factory の破棄」になっていること。
- スレッドの終了待ちとネイティブリソース破棄の間に GIL を解放していること。
- 破棄順序を変更してはならない理由がコメントで明示されていること。
- 修正前に SIGSEGV が再現していた E コア限定並列ストレス（100 回以上）で SIGSEGV が発生しないこと。
- 既存の e2e テストが引き続き通ること。

