# SoraAudioSinkImpl::AppendData が on_format_ / on_data_ を GIL 非保持で呼ぶ未定義動作を修正する

- Priority: Low
- Created: 2026-06-02
- Model: Opus 4.8
- Branch: feature/fix-append-data-callback-missing-gil

## pending にした理由

`on_format_` / `on_data_` はヘッダ (`src/sora_audio_sink.h:66-72`) に「コールバックと
Read 関数の共存はパフォーマンスや使い方の面で難しいことが判明したので、
`on_data_`, `on_format_` ともに廃止予定」と明記された **廃止予定の API** である。
そのため、本問題は次のいずれを採るかの設計判断が必要であり、判断が固まるまで
pending とする。

- A. GIL 取得 (`gil_scoped_acquire`) を追加して未定義動作を解消する (他のコール
  バックと同じ規約に揃える)。
- B. 廃止予定であることを踏まえ、`on_format_` / `on_data_` 自体を削除する (後方
  互換のない変更になるため別途段取りが必要)。

どちらにするか、また削除する場合の互換性・告知の段取りが決まっていないため、本
issue は修正せずそのまま残す。

なお本問題は issue 0012「SoraAudioSinkImpl::Read が待機中に GIL を保持し続ける問題
を修正する」の調査中に発見し、0012 のスコープ外として切り出したものである。

## 目的

`SoraAudioSinkImpl::AppendData` (`src/sora_audio_sink.cpp:102-135`) は、GIL を保持
しない WebRTC オーディオスレッドから呼ばれるにもかかわらず、`on_format_` /
`on_data_` の Python コールバックを GIL を取得せずに呼んでいる。これは Python C
API の利用規約違反 (未定義動作) であり、参照カウント競合によるメモリ破壊で
プロセスが SIGSEGV でクラッシュしうる。issue 0009 (`SoraConnection::OnPush` の GIL
未取得) と同種の問題である。

`on_format_` / `on_data_` を設定したアプリでのみ顕在化するが、設定された場合は
コールバックが呼ばれるたびに未定義動作が確定的に発生する。

## 優先度根拠

Low とする。

- `on_format_` / `on_data_` は廃止予定であり、既定では未設定。問題が起きるのは
  これらを明示的に設定したアプリに限られる。
- 一方で、設定した場合は確定的に未定義動作となり、native レイヤのクラッシュは
  Python 例外として捕捉できない (issue 0009 と同じ性質)。
- 廃止予定 API のための修正であり、投資対効果が読みにくいことから Low とし、
  pending で設計判断を待つ。

## 現状

### 根本原因

`AppendData` は `OnData` (`webrtc::AudioTrackSinkInterface::OnData`,
`src/sora_audio_sink.cpp:51`) から呼ばれる。`OnData` は GIL を保持しない WebRTC
オーディオスレッドから呼ばれるコールバックである (関数内に `gil_scoped_acquire`
は無い)。その `AppendData` 内で、GIL を取得しないまま Python callable を呼んでいる
箇所が 2 つある。

```cpp
// src/sora_audio_sink.cpp:114-116 (buffer_mtx_ 保持中)
if (on_format_) {
  call_python(on_format_, sample_rate_, number_of_channels_);
}
```

```cpp
// src/sora_audio_sink.cpp:128-134
if (on_data_) {
  size_t shape[2] = {number_of_frames, number_of_channels_};
  auto data = nb::ndarray<nb::numpy, int16_t, nb::shape<-1, -1>>(
      (void*)audio_data, 2, shape, nb::handle());
  call_python(on_data_, data);
}
```

- `on_format_` は `std::function<void(int, size_t)>`、`on_data_` は
  `std::function<void(nb::ndarray<...>)>` で、いずれも Python 側で設定された
  Python callable を保持する (`src/sora_sdk_ext.cpp` の `.def_rw("on_data", ...)` /
  `.def_rw("on_format", ...)`)。これらを呼ぶと Python C API に降りる。
- `call_python` (`src/sora_call.h`) は呼び出しを try/catch で包むだけで GIL は
  取得しない。GIL の取得は呼び出し側の責務。
- さらに `on_data_` の `nb::ndarray` 構築 (`:130-131`) 自体も Python C API であり
  GIL が必要。
- 特に `on_format_` の呼び出しは `buffer_mtx_` を保持したまま行われる
  (`:107` の `unique_lock` のスコープ内)。GIL を取得する形に直す場合は、
  `buffer_mtx_` 保持中に GIL を取りに行くことになるため、`Read` 側のロック順序
  (GIL → `buffer_mtx_`) との逆転 (デッドロック) に注意する必要がある。

GIL を取得せずに Python C API を呼ぶと、参照カウント操作などが GIL を保持して
Python を実行している別スレッドと競合し、解放済みオブジェクト参照やヒープ破壊と
いった形でメモリ安全性が壊れうる。破壊はコールバック内に留まらず、後続の任意の
Python 処理で SIGSEGV として顕在化しうる (issue 0009 と同じ機序)。

### 利用側で回避できるか

回避できない。コールバックを呼ぶスレッドや GIL の保持は SDK 内部の責務で、利用側
から制御する API はない。利用側は `on_format` / `on_data` を設定するだけで、ハンド
ラがどのスレッド・GIL 状態で呼ばれるかには関与できない。

## 設計方針

pending のため確定しない。A 案 (GIL 取得追加) を採る場合の骨子のみ記す。

- `AppendData` 内で `on_format_` / `on_data_` を呼ぶ直前に GIL を取得する
  (`gil_scoped_acquire`)。`nb::ndarray` 構築も GIL 保持下で行う。
- ロック順序に注意する。`on_format_` は現在 `buffer_mtx_` 保持中に呼ばれるため、
  GIL を取得すると `buffer_mtx_` → GIL の順になり、`Read` の GIL → `buffer_mtx_`
  と逆転してデッドロックしうる。GIL 取得を `buffer_mtx_` のスコープ外に出すなど、
  ロック順序を一貫させる対応が必要。
- B 案 (削除) を採る場合は、後方互換のない変更として段取り (告知・メジャー
  バージョン) を別途検討する。

## 完了条件

pending のため確定しない。A 案を採る場合は以下を満たすこと。

- `AppendData` が `on_format_` / `on_data_` を呼ぶ際に GIL を取得していること。
- `Read` とのロック順序が逆転せずデッドロックしないこと。
- ビルドが通り、既存テストが全て通ること。
- `CHANGES.md` の `## develop` に `[FIX]` エントリを担当者行付きで追記している
  こと。

## 関連 issue

- `issues/closed/0009-bug-fix-on-push-missing-gil.md`: 同種の「GIL 非保持で Python
  コールバックを呼ぶ未定義動作」。本 issue の手本となる先例。
- `issues/0012-bug-fix-audio-sink-read-holds-gil.md` (または closed): 本 issue の
  発見契機。0012 のスコープ外として切り出した。
