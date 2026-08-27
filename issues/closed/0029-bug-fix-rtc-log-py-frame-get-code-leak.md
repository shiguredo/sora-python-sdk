# RtcLog で PyFrame_GetCode の新参照を Py_DECREF せず参照リークしている問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Completed: 2026-07-27
- Model: Opus 4.7
- Branch: feature/fix-rtc-log-py-frame-get-code-leak

## 目的

`src/sora_log.cpp` の `RtcLog` 関数は libwebrtc のログを出力するたびに Python の呼び出し元ファイル名・行番号を取得しているが、`PyFrame_GetCode` が返す新参照 (new reference) を `Py_DECREF` で解放していない。`RtcLog` はライブラリのログ経路として実行中に多数回呼ばれるため、放置すると `PyCodeObject` の参照カウントが単調増加し、Python 側の GC からも解放されない静かな参照リークになる。長時間稼働するアプリケーションではメモリ使用量が漸増し、特に頻繁にログが出る状況や RtcLog をユーザコードから呼んでいる状況で顕在化する。本 issue で参照リークを止め、合わせて GIL 取得状況の整合性も確認する。

## 優先度根拠

Medium とする。

- 1 回あたりのリーク量は `PyCodeObject` 1 個分と小さく即時のクラッシュには直結しないが、`RtcLog` は libwebrtc のログを Python 側に流す経路として定常的に呼ばれる関数であり、長時間稼働するサーバ用途で確実にメモリ使用量を蓄積させる。
- 修正は `Py_DECREF(code);` を 1 行追加する規模で、副作用やリスクが極めて小さい。
- ただし内部 API の生 C-API 呼び出しに起因するメモリ管理バグであり、放置するほど性質が悪い (発見しづらい・他箇所への波及検証も必要になる) ため High ではなく Medium 相当として優先的に潰す。

## 現状

`src/sora_log.cpp` の `RtcLog` 関数は以下の通り。

```cpp
void RtcLog(webrtc::LoggingSeverity severity, const std::string& message) {
  // Python のどこから呼ばれたかを一緒に出力する
  PyFrameObject* frame = PyEval_GetFrame();
  if (frame != nullptr) {
    PyCodeObject* code = PyFrame_GetCode(frame);
    const char* filename = PyUnicode_AsUTF8(code->co_filename);
    int lineno = PyFrame_GetLineNumber(frame);
    RTC_LOG_V(severity) << "[" << filename << ":" << lineno << "] " << message;
  } else {
    RTC_LOG_V(severity) << message;
  }
}
```

- CPython のドキュメントおよびヘッダ (`Python.h`) の規約上、`PyFrame_GetCode` は **新参照 (new reference) を返す** API である (旧来の `frame->f_code` 直接アクセスは Python 3.11 で削除され、後継としてこの関数が用意された)。
- 上記コードでは `PyFrame_GetCode` の戻り値 `code` を `Py_DECREF(code);` で解放しておらず、`RtcLog` が呼ばれるたびに `PyCodeObject` の参照カウントが 1 ずつ増える。`PyCodeObject` 自体は通常モジュール由来でアプリ終了まで生存するが、参照カウントが増え続ければ静的解析ツールや valgrind に検出され、長時間稼働では計測上のリーク量が無視できなくなる。
- 加えて `PyFrame_GetCode` / `PyUnicode_AsUTF8` / `PyFrame_GetLineNumber` はいずれも GIL を保持した状態で呼ぶ必要がある Python C-API である。`RtcLog` は libwebrtc 側のスレッド (signaling / network / worker など) からも呼ばれる経路があり、GIL を保持していない状態でこれらの API を呼ぶと未定義動作 (クラッシュ・データ競合) を起こす可能性がある。本修正と同時に GIL の保持状況を確認する。

## 設計方針

- `PyFrame_GetCode` の戻り値を使い終わった直後に `Py_DECREF(code);` を呼び、新参照を確実に解放する。`filename` は `code->co_filename` から取り出した内部表現を参照しているため、`Py_DECREF(code);` は `RTC_LOG_V` でログ文字列を組み立てた **後** に置くか、あらかじめ `filename` を `std::string` にコピーしてから `Py_DECREF` するかのいずれかとする。CPython の `PyUnicode_AsUTF8` が返すポインタは元の `PyObject` の生存期間に紐付くため、生存期間管理を取り違えないこと。
- `RtcLog` の呼び出し元を `src/` 配下で精査し、libwebrtc の内部スレッド (signaling / network / worker) など GIL を保持しないスレッドから呼ばれる経路がないか確認する。経路がある場合は `gil_scoped_acquire` (本リポジトリの `src/gil.h` に既存) で囲み、Python C-API 呼び出し区間を GIL 保持下に揃える。
- `PyEval_GetFrame` は GIL 保持時のみ有効な API であり、GIL 非保持での呼び出しは未定義動作。GIL を取れない経路では `RtcLog` を Python フレーム取得抜きで呼ぶフォールバックも検討する。

## 完了条件

- `RtcLog` を多数回呼ぶ経路で `PyCodeObject` の参照カウントが単調増加しないこと (テストや手元検証で確認)。
- 修正後に `RtcLog` を高頻度で呼んでも RSS が単調増加し続けないこと (長時間稼働や反復実行で確認)。
- libwebrtc 側の非 Python スレッドからの呼び出し経路がある場合は、GIL 保持の整合が取れていること (`gil_scoped_acquire` の付与など)。
- 既存の e2e テストおよびユニットテストが引き続き通ること。

## 解決方法

`RtcLog` で `PyFrame_GetCode` が返す新参照を、ログ組み立て後に `Py_DECREF` するようにした。

- `PyUnicode_AsUTF8` のポインタは `code` 生存期間に紐付くため、`filename` を先に `std::string` へコピーしてから解放する
- Python C-API 呼び出し全体を `gil_scoped_acquire` で囲む
- 呼び出し元を精査したところ、`RtcLog` は Python 公開 API (`rtc_log`) 経由のみで、C++ 内部スレッドからの直接呼び出しは無かった

追加したテスト:

- `tests/test_rtc_log_refcount.py`
  - `rtc_log` を 1000 回呼んでも呼び出し元 `PyCodeObject` の `sys.getrefcount` が増えないことを検証する
  - 修正前は 100 回で +100、修正後は delta 0 を手元で確認した

変更履歴は `CHANGES.md` の `## develop` に `[FIX]` として追記した。
