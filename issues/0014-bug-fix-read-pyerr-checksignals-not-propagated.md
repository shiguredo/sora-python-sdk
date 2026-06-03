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
例外を送出したとき (-1 を返し、エラー指示子がセットされる)。このとき現状コードは
`(False, None)` を正常 return するため、**エラー指示子がセットされたまま C++ 関数が
正常終了する**。これは Python C API の規約 (「エラー指示子がセットされた状態で正常値を
返してはならない」) に反する。

意図としては「シグナルで待機を中断したら `read()` をタイムアウト同様に `(False, None)`
で返す」ことだったと思われるが、シグナルハンドラが送出した例外 (KeyboardInterrupt 等)
は本来呼び出し側へ伝播すべきであり、握り潰すのは不適切。

### 補足: nanobind の挙動確認が必要

エラー指示子をセットしたまま nb::tuple を返したとき、nanobind が実際にどう振る舞うか
(例外を伝播するのか、SystemError 等に化けるのか、エラー指示子が残るのか) は本リポジトリ
のコードからは断定できない。修正方針を決める前に、nanobind のバージョン
(`CHANGES.md` 記載の `2.12.0`) での挙動を確認すること。

### 関連

- issue 0012 (`SoraAudioSinkImpl::Read` の GIL 解放) で `Read` の待機まわりを変更したが、
  この `PyErr_CheckSignals()` 分岐自体は変更しておらず、本問題は 0012 修正後も残る。
- 本問題は 0012 のコードレビュー中に発見し、スコープ外として切り出した。

## 設計方針

`PyErr_CheckSignals()` が 0 以外を返した (= 例外がセットされた) 場合は、`(False, None)`
を返すのではなく、セットされた Python 例外を**伝播する**。nanobind では
`throw nb::python_error();` で「現在セットされているエラー指示子」を C++ 例外として
送出でき、これが Python 側へ正しく伝播する想定。

- predicate 内では例外を投げず (predicate から throw すると `wait_for` の途中で
  スタックを巻き戻すことになり扱いが難しい)、predicate は従来どおり真を返して
  `wait_for` を抜け、待機後の明示チェックで `PyErr_CheckSignals()` を再評価して
  伝播する形に寄せる。タイムアウト経路 (`wait_for` が false 復帰) では従来どおり
  `(False, None)` を返す。
- 具体的なコードは nanobind の挙動確認 (上記「補足」) を踏まえて確定する。

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
