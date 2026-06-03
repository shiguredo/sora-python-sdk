# SoraAudioSinkImpl::Read がシグナル割り込み時に Python 例外を握り潰す問題を修正する

- Priority: Low
- Created: 2026-06-03
- Model: Opus 4.8
- Branch: feature/fix-read-pyerr-checksignals-not-propagated

## 目的

`SoraAudioSinkImpl::Read` (`src/sora_audio_sink.cpp`) は `wait_for` の predicate と
待機後の両方で `PyErr_CheckSignals()` を呼び、シグナル割り込み (Ctrl-C 等) で待機を
抜けられるようにしている。しかし `PyErr_CheckSignals()` がシグナルハンドラの送出した
例外を検出 (戻り値が 0 以外) したとき、その**例外を処理 (伝播もクリアも) しないまま
`(False, None)` タプルを正常 return している**。

```cpp
// src/sora_audio_sink.cpp (Read 内)
if (PyErr_CheckSignals() != 0) {
  // Signals で wait を抜けた時は返す
  return nb::make_tuple(false, nb::none());
}
```

`PyErr_CheckSignals()` は、シグナルハンドラ (既定の SIGINT → KeyboardInterrupt 等)
が例外を送出した場合に -1 を返し、**Python のエラー指示子 (error indicator) をセット
した状態にする**。この状態で正常値を返すのは Python C API の規約違反であり、本来
ユーザーが期待する「`read()` 中の Ctrl-C で KeyboardInterrupt が上がる」挙動にも
ならない。

本 issue は、シグナルでセットされた例外を握り潰さず、適切に伝播するよう修正する。

## 優先度根拠

Low とする。

- 顕在化条件が限定的。`PyErr_CheckSignals()` は**メインスレッドでのみ**シグナルを
  処理し、非メインスレッドでは何もせず 0 を返す (CPython の仕様)。したがって本問題
  は「`read()` をメインスレッドで呼び、その待機中にシグナル (Ctrl-C 等) が届く」場合
  にのみ起こる。ワーカースレッドで `read()` する一般的な使い方では踏まない。
- クラッシュやメモリ破壊ではなく、「Ctrl-C 時に KeyboardInterrupt がそのまま上がらず、
  エラー指示子をセットしたまま正常値を返す不整合」に留まる。ただしエラー指示子を
  セットしたまま return すると、nanobind 側で予期しない例外 (SystemError 等) に化けたり、
  後続の無関係な Python 処理で例外が顕在化したりして、デバッグを難しくする可能性がある。
- 修正は `Read` 内の数行に閉じ、影響範囲が小さい。

## 現状

### 根本原因

`Read` (`src/sora_audio_sink.cpp`) には `PyErr_CheckSignals()` を呼ぶ箇所が 2 つある。

1. `wait_for` の predicate 内:

```cpp
[&] {
  return (number_of_channels_ > 0 &&
          buffer_.size() >= frames * number_of_channels_) ||
         PyErr_CheckSignals() != 0;
}
```

predicate が真になり `wait_for` を抜けたあと、

2. 待機後の明示チェック:

```cpp
if (PyErr_CheckSignals() != 0) {
  // Signals で wait を抜けた時は返す
  return nb::make_tuple(false, nb::none());
}
```

`PyErr_CheckSignals()` の戻り値が 0 以外になるのは、保留シグナルのハンドラが Python
例外を送出したとき (-1 を返し、エラー指示子がセットされる)。

実際の不具合の流れはより厄介で、`PyErr_CheckSignals()` が冪等でないことに起因する。

1. predicate 内の `PyErr_CheckSignals()` が SIGINT を処理して KeyboardInterrupt を
   セットし -1 を返す。同時に内部の "tripped" フラグがクリアされる。predicate は真を
   返して `wait_for` を抜ける。
2. 待機後の 2 回目 `PyErr_CheckSignals()` は、tripped フラグが既にクリア済みのため
   **0 を返す**。そのため `if (PyErr_CheckSignals() != 0)` の分岐に入らず、エラー指示子を
   セットしたまま通常の読み出し経路へ進み、最終的に `(true, output)` を返してしまう。

いずれにせよ **エラー指示子がセットされたまま C++ 関数が non-null を返す**点が問題で、
これは Python C API の規約 (「エラー指示子がセットされた状態で正常値を返してはならない」)
に反する。シグナルハンドラが送出した例外 (KeyboardInterrupt 等) は本来呼び出し側へ
伝播すべきであり、握り潰すのは不適切。

### 補足: nanobind の挙動確認 (確認済み)

nanobind `2.12.0` のソース (`src/error.cpp` / `src/nb_func.cpp`) を確認した結果は以下。

- `throw nb::python_error();` は正しく機能する。`python_error` のコンストラクタは
  `PyErr_GetRaisedException()` (Python 3.12+) でエラー指示子を吸い出してクリアし、
  関数ディスパッチャ (`nb_func.cpp` の `catch (python_error &e) { e.restore(); }`) が
  `PyErr_SetRaisedException()` で復元して `result == nullptr` で返すため、Python 側へ
  正しく例外が伝播する。
- 現状バグ (エラー指示子をセットしたまま non-null の tuple を返す) では、ディスパッチャ
  は戻り値変換が成功すると tuple をそのまま返しエラー指示子をチェックしない。このため
  CPython の `_Py_CheckFunctionResult` が
  `SystemError: ... returned a result with an exception set` を送出する。issue が推測して
  いた「SystemError 等に化ける」が裏付けられた。
- `GILMutexLock` (issue 0012 で導入) 保持中に throw しても、そのデストラクタは mutex のみ
  解放し GIL は保持したまま巻き戻るため、ディスパッチャに届く時点で GIL も保持されており
  整合する。

### 関連

- issue 0012 (`SoraAudioSinkImpl::Read` の GIL 解放) で `Read` の待機まわりを変更したが、
  この `PyErr_CheckSignals()` 分岐自体は変更しておらず、本問題は 0012 修正後も残る。
- 本問題は 0012 のコードレビュー中に発見し、スコープ外として切り出した。

## 設計方針

シグナルでエラー指示子がセットされた場合は、`(False, None)` を返すのではなく、
セットされた Python 例外を**伝播する**。nanobind では `throw nb::python_error();` で
「現在セットされているエラー指示子」を C++ 例外として送出でき、これが Python 側へ
正しく伝播する (上記「補足」で確認済み)。

- predicate 内では例外を投げない (predicate から throw すると `wait_for` の途中で
  スタックを巻き戻すことになり扱いが難しい)。predicate は従来どおり真を返して
  `wait_for` を抜ける。
- 待機後の明示チェックは `PyErr_CheckSignals()` の戻り値ではなく **`PyErr_Occurred()`**
  で判定する。理由: `PyErr_CheckSignals()` は冪等ではない。predicate 内の
  `PyErr_CheckSignals()` が保留シグナルを処理した時点で内部の "tripped" フラグが
  クリアされるため、待機後に `PyErr_CheckSignals()` を再度呼んでも 0 を返してしまい、
  predicate でセットされたエラー指示子を検出できない (現状バグの実際の挙動でもある)。
  `PyErr_Occurred()` はエラー指示子の有無を見るだけで冪等なため、predicate が立てた
  例外を確実に拾える。

```cpp
// wait_for を抜けた後 (タイムアウトでない)。predicate 内の PyErr_CheckSignals() が
// シグナル例外をセットしていれば、それを握り潰さず伝播する。
if (PyErr_Occurred()) {
  throw nb::python_error();
}
```

- 通常経路 (バッファ充足で抜けた場合) はエラー指示子が無いため throw されず従来どおり。
- タイムアウト経路 (`wait_for` が false 復帰) は従来どおり `(False, None)` を返す。

## 完了条件

- `Read` の待機中にメインスレッドで Ctrl-C (SIGINT) を送った際、`read()` が
  KeyboardInterrupt を送出する (エラー指示子をセットしたまま正常値を返さない) こと。
- シグナルが無い通常のタイムアウト経路は従来どおり `(False, None)` を返すこと。
- ビルドが通り、既存テストが全て通ること。
- `CHANGES.md` の `## develop` に `[FIX]` エントリを担当者行付きで追記していること。

## 関連 issue

- `issues/0012-bug-fix-audio-sink-read-holds-gil.md` (または closed): 本問題の発見契機。
- `issues/closed/0009-bug-fix-on-push-missing-gil.md`: 同じく Read / コールバック周辺の
  Python C API 規約に関する修正の先例。
