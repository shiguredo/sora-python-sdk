# SoraAudioSinkImpl::Read がシグナル割り込み時に Python 例外を握り潰す問題を修正する

- Priority: Medium
- Created: 2026-06-03
- Polished: 2026-06-03
- Model: Opus 4.8
- Branch: feature/fix-read-pyerr-checksignals-not-propagated

## 前提 (依存関係)

本 issue は issue 0012 (`SoraAudioSinkImpl::Read` の GIL 解放、PR #293) が develop に
マージされた後のコードを基準に書く。0012 は `Read` の待機まわりを `std::unique_lock` +
`std::condition_variable` から、GIL と `buffer_mtx_` を束ねた合成ロック `GILMutexLock` +
`std::condition_variable_any` へ変更する (型名 `GILMutexLock` は PR #293 で確定済み)。
本問題は 0012 ではこの `PyErr_CheckSignals()` 分岐を変更しないため、0012 マージ後も残る。

CLAUDE.md「番号が小さい issues から順番に対応する」に従い、0012 (PR #293) のマージ後に
着手すること。ブランチは develop から派生する。

着手は 0012 (PR #293) マージ後とする (完了条件にも明記)。なお修正方針 (`PyErr_Occurred()` +
`throw nb::python_error();`) の正当性自体は、throw 時に GIL が保持されているという点で 0012
マージ前後のどちらのコード基盤でも変わらない (詳細は後述「補足」)。これは方針の頑健性の
説明であって、マージ前に着手してよいという意味ではない。

## 目的

`SoraAudioSinkImpl::Read` (`src/sora_audio_sink.cpp`) は `wait_for` の predicate と待機後の
両方で `PyErr_CheckSignals()` を呼び、シグナル割り込み (Ctrl-C 等) で待機を抜けられるように
している。しかしシグナルハンドラ (既定の SIGINT → KeyboardInterrupt 等) が送出した例外を
**呼び出し側へ伝播せず握り潰し、Python のエラー指示子 (error indicator) をセットしたまま
C++ 関数が正常値 (non-null tuple) を返している**。これは Python C API の規約 (「エラー指示子を
セットした状態で正常値を返してはならない」) 違反であり、「`read()` 中の Ctrl-C で
KeyboardInterrupt が上がる」という本来の挙動にもならない。

本 issue は、シグナルでセットされた例外を握り潰さず適切に伝播するよう修正する。なお
タイトルは「例外の握り潰し」を表すが、後述のとおりこの握り潰しは読み出し経路のバッファ外
アクセス (メモリ破壊) も誘発するため、実害は例外伝播の不整合に留まらない。

## 優先度根拠

Medium とする。

- 顕在化条件は限定的。`PyErr_CheckSignals()` は**メインスレッドでのみ**シグナルを処理し、
  非メインスレッドでは何もせず 0 を返す (CPython の仕様)。したがって本問題は「`read()` を
  メインスレッドで呼び、その待機中にシグナル (Ctrl-C 等) が届く」場合にのみ起こる。
  ワーカースレッドで `read()` する使い方では踏まない。
- ただし単なる「例外の握り潰し」に留まらず、**メモリ安全性を壊しうる** (後述「根本原因」)。
  シグナルで predicate を抜けた時点ではバッファが要求フレーム数に満たないまま読み出し経路へ
  進み、`memcpy` がバッファ外を読み、`buffer_.size() - num_of_samples` が `size_t` で
  アンダーフローして `memmove` が巨大領域をコピーする。プロセスクラッシュやヒープ破壊に
  至りうる。Low ではなく Medium とする主因はこの点。
- 一方で、メインスレッドの `read()` 待機中という限定条件でしか発火せず、全プラットフォームで
  確定的にクラッシュするわけではないため High とはしない。
- 修正は `Read` 内の数行に閉じ、影響範囲は小さい。

## 現状

### 根本原因

0012 マージ後の `Read` (`src/sora_audio_sink.cpp`) には `PyErr_CheckSignals()` を呼ぶ箇所が
2 つある。

1. `wait_for` の predicate 内:

```cpp
[&] {
  return (number_of_channels_ > 0 &&
          buffer_.size() >= frames * number_of_channels_) ||
         PyErr_CheckSignals() != 0;
}
```

2. 待機後の明示チェック:

```cpp
if (PyErr_CheckSignals() != 0) {
  // Signals で wait を抜けた時は返す
  return nb::make_tuple(false, nb::none());
}
```

`PyErr_CheckSignals()` は、保留シグナルのハンドラが Python 例外を送出すると -1 を返し、
エラー指示子をセットする。問題は **`PyErr_CheckSignals()` が冪等でない**ことに起因する。

1. predicate 内の `PyErr_CheckSignals()` が SIGINT を処理して KeyboardInterrupt をセットし
   -1 を返す。このとき内部の "tripped" フラグはクリアされる。predicate は真を返し
   `wait_for` を抜ける (CPython のシグナル処理仕様。`refs/` に一次資料が無いため、実装着手時に
   再現確認すること)。
2. 待機後の 2 回目 `PyErr_CheckSignals()` は、tripped フラグが既にクリア済みのため **0 を
   返す**。よって `if (PyErr_CheckSignals() != 0)` の分岐に入らない。

結果、エラー指示子をセットしたまま通常の読み出し経路へ進む。さらにこの経路は危険で、
predicate がシグナルで真になった場合 (バッファ充足の項は OR の短絡で評価されておらず偽)、
`buffer_.size() < frames * number_of_channels_` のまま `num_of_samples = frames *
number_of_channels_` を計算する。`number_of_channels_ > 0` のとき:

- `memcpy(output_data, buffer_.data(), num_of_samples * sizeof(int16_t))` がバッファ末尾を
  超えて読み出す (buffer over-read)。
- `buffer_.size() - num_of_samples` が `size_t` でアンダーフローし、`memmove` が巨大領域を
  コピーする。さらに続く `buffer_.SetSize(buffer_.size() - num_of_samples)` も同じ巨大値を
  受け、`webrtc::BufferT` の内部で `new` が巨大確保を試みて `std::bad_alloc` に至る経路もある。

`wait_for` の待機"中"は `condition_variable_any` が `lock` (`buffer_mtx_`) を解放するため、
待機中は `AppendData` が割り込める。しかし predicate がシグナルで真を返して `wait_for` を
抜けた後は、`lock` を再取得した状態で読み出し (memcpy) まで `buffer_mtx_` を連続保持する。
このため「抜けた時点でのバッファ不足」が読み出しまで持続し、`AppendData` で充足することは
ないので、この over-read は確実に発生する。すなわち本問題は「例外の握り潰し」かつ
「メモリ安全性の破壊」である。

いずれにせよ **エラー指示子がセットされたまま C++ 関数が non-null を返す**点が Python C API
規約違反であり、シグナルハンドラが送出した例外 (KeyboardInterrupt 等) は本来呼び出し側へ
伝播すべきである。

### 補足: nanobind の挙動確認 (確認済み)

修正方針の妥当性を nanobind `2.12.0` のソース (`src/error.cpp` / `src/nb_func.cpp`) で確認した
(`pyproject.toml` の `requires-python >= 3.12` より、Python 3.12+ 経路のみ検証すれば足りる)。

- `throw nb::python_error();` は正しく機能する。`python_error` のコンストラクタは
  `PyErr_GetRaisedException()` でエラー指示子を吸い出してクリアし、関数ディスパッチャ
  (`nb_func.cpp` の `catch (python_error &e) { e.restore(); }`) が `PyErr_SetRaisedException()`
  で復元して `result == nullptr` で返すため、Python 側へ正しく例外が伝播する。
- 現状バグ (エラー指示子をセットしたまま non-null の tuple を返す) では、ディスパッチャは
  戻り値変換が成功すると tuple をそのまま返しエラー指示子をチェックしない。このため CPython の
  `_Py_CheckFunctionResult` が `SystemError: ... returned a result with an exception set` を
  送出する (ソース読みからの帰結。実機での確認は実装時に行うこと)。
- throw 時のスタック巻き戻しで `GILMutexLock` (0012 で導入) のデストラクタが `buffer_mtx_` を
  解放する。`GILMutexLock` のデストラクタは mutex のみ解放し GIL には触れない (内包する
  `GILLock` のデストラクタは GIL 状態を復元しない自明なもの) ため、GIL を保持したまま巻き戻り、
  ディスパッチャに GIL 保持で届くので整合する。

## 設計方針

シグナルでエラー指示子がセットされた場合は握り潰さず、セットされた Python 例外を**伝播する**。
nanobind では `throw nb::python_error();` で現在のエラー指示子を C++ 例外として送出でき、
これが Python 側へ正しく伝播する (上記「補足」で確認済み)。

- predicate 内では例外を投げない (predicate から throw すると `wait_for` の途中でスタックを
  巻き戻すことになり扱いが難しい)。predicate は従来どおり真を返して `wait_for` を抜ける。
- 待機後の判定は `PyErr_CheckSignals()` の戻り値ではなく **`PyErr_Occurred()`** で行う。
  理由は「根本原因」のとおり `PyErr_CheckSignals()` が冪等でなく、待機後の 2 回目呼び出しでは
  predicate が立てた例外を検出できないため。`PyErr_Occurred()` はエラー指示子の有無を見るだけで
  冪等なので確実に拾える。
- この判定は `wait_for` の戻り値 (タイムアウト/充足) を見る前に置く。タイムアウト直前に
  シグナルが処理されエラー指示子が残るケースも取りこぼさないため。

```cpp
// timeout_ns は説明用の擬似変数。実コードでは現状どおり
// std::chrono::nanoseconds((int64_t)((double)timeout * 1000. * 1000. * 1000.)) を
// wait_for にインラインで渡し、predicate もラムダをインライン展開する。
bool ready = buffer_cond_.wait_for(lock, timeout_ns, predicate);
// 待機を抜けた理由に関わらず、predicate 内の PyErr_CheckSignals() がシグナル例外を
// セットしていれば、それを握り潰さず伝播する。
if (PyErr_Occurred()) {
  throw nb::python_error();
}
if (!ready) {
  // タイムアウトで返す
  return nb::make_tuple(false, nb::none());
}
```

エッジケース:

- バッファ充足とシグナルが同時に成立した場合: predicate は `||` の短絡でバッファ充足側を真と
  評価して抜けるため `PyErr_CheckSignals()` を呼ばない。`PyErr_Occurred()` は偽となり、データを
  通常どおり返す。保留シグナルは次の Python バイトコード境界で処理されるので握り潰しにはならない。
- 通常経路 (バッファ充足で抜けた場合): エラー指示子が無いため throw されず従来どおり。

## 後方互換

メインスレッドで `read()` の待機中に Ctrl-C を押したときの挙動が、(現状の不正な non-null
返却) から **KeyboardInterrupt の送出** に変わる。これは異常系を正しい挙動に直す修正であり、
規約違反・メモリ破壊を伴う現状を正常化するものなので `[FIX]` 扱いとし、`[CHANGE]` (後方互換の
ない変更) には該当しないと判断する。`read()` の API・シグネチャ・戻り値型は不変で、正常系
(タイムアウト / データ取得) の挙動も変わらない。

## テスト方針

性質の異なる 2 種類を区別する (issue 0009 / 0012 と同じ整理)。

1. メモリ破壊を確定的に再現するテスト: 追加しない。メインスレッドの `read()` 待機中という
   タイミングに依存し、再現を安定させにくい。
2. シグナル例外伝播を機能的に検証するテスト: 次の構成なら原理的に書ける。
   - sink 取得は 0012 のテスト (`tests/test_audio_sink_read_gil.py`) と同じく sendonly +
     recvonly の 2 接続を使う。
   - **メインスレッド**で `read(frames>0, timeout=長め)` を呼んでブロックさせ、別スレッドから
     一定遅延後に `signal.raise_signal(signal.SIGINT)` を撃つ。修正後はメインスレッドの
     `read()` が `KeyboardInterrupt` を送出することを `pytest.raises` で確認する。修正前は、
     over-read が先に刺さればクラッシュ (未定義動作)、刺さらなければエラー指示子を残したまま
     non-null を返して `_Py_CheckFunctionResult` 由来の `SystemError` になる、のいずれか
     (「根本原因」「補足」参照)。いずれにせよ修正後の KeyboardInterrupt とは異なる。
   - 例外伝播のみを見るなら、音声データが無い (`number_of_channels_ == 0`) 状態でもよい。この場合
     `num_of_samples` は 0 になり over-read は起きないが、predicate はシグナルで真になるため
     伝播経路は検証できる。
   - ただしメインスレッドでの SIGINT は pytest 自身のシグナル処理と干渉しうるため、安定して
     書けない場合は本テストの追加を必須としない。

以上より、本修正の正当性は「コード検査による根本原因の確定」と「nanobind の伝播経路の確認」に
置き、(2) の機能テストは安定に書ける範囲で追加する任意項目とする。

## 完了条件

- 0012 (PR #293) が develop にマージされた後のコードに対して修正していること。
- `Read` の待機を抜けた際にエラー指示子がセットされていれば、`(False, None)` や non-null tuple を
  返さず `throw nb::python_error();` で Python 例外を伝播すること。特にメインスレッドで `read()`
  待機中に Ctrl-C (SIGINT) を送ると `read()` が KeyboardInterrupt を送出すること。
- シグナルが無い通常のタイムアウト経路は従来どおり `(False, None)` を返すこと。
- ビルドが通り、既存テストが全て通ること。
- `CHANGES.md` の `## develop` に `[FIX]` エントリを担当者行付きで追記していること
  (CLAUDE.md の種別順・書式に従う)。

## 関連 issue

- `issues/0012-bug-fix-audio-sink-read-holds-gil.md` (PR #293。現時点では未マージで `issues/`
  直下。マージ完了で `issues/closed/` へ移動予定): 本問題の発見契機。`Read` の待機まわりと
  `GILMutexLock` を導入する。
- `issues/closed/0009-bug-fix-on-push-missing-gil.md`: Read / コールバック周辺の Python C API
  規約に関する修正の先例。
