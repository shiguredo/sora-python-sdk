# `SoraAudioFrameTransformer::Transform` と `SoraVideoFrameTransformer::Transform` で GIL を取得せずに `on_transform_` を呼ぶ問題を修正する

- Priority: High
- Created: 2026-06-23
- Polished: 2026-07-13
- Model: Opus 4.7
- Branch: feature/fix-frame-transformer-missing-gil

## 目的

`SoraAudioFrameTransformer::Transform` と `SoraVideoFrameTransformer::Transform` は、libwebrtc のエンコーダー / デコーダーワーカースレッドから呼ばれる `webrtc::FrameTransformerInterface::Transform` の override である。
現在は GIL を取得せずに Python callable を保持する `on_transform_` を直接呼んでいる。

`std::make_unique<SoraTransformableAudioFrame>` と `std::make_unique<SoraTransformableVideoFrame>` は C++ のラッパーオブジェクトを構築するだけであり、それ自体を Python オブジェクトの構築とは表現しない。
一方、`std::function` による Python callable の呼び出し、nanobind による引数変換、callback 内の `get_data()` / `set_data()` / `enqueue()`、NumPy 配列の操作は Python C API と参照カウントに触れるため、GIL を保持して実行しなければならない。

GIL 非保持でこの経路を実行すると、Encoded Transform を有効にした送信側または受信側で未定義動作が発生し、プロセスのクラッシュやヒープ破壊につながる。

## 優先度根拠

High とする。

- `SoraAudioFrameTransformer` と `SoraVideoFrameTransformer` は現在も nanobind バインディングと型スタブで公開されている。
- `tests/test_encoded_transform.py` は送信側・受信側の Audio / Video の 4 経路で `on_transform` を設定し、callback 内でフレームの読み出し、変更、`enqueue` を実行している。
- 問題が発生するのは特定の廃止予定 API ではなく、現在公開している Encoded Transform の基本経路である。
- native レイヤで GIL を取得しない Python C API 呼び出しは Python 例外として回復できず、正式リリース前に解消する必要がある。

## 現状

### Audio / Video の `Transform`

`src/sora_frame_transformer.h:258-269` の Audio 実装は次のとおりである。

```cpp
void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                   transformable_frame) override {
  on_transform_(std::make_unique<SoraTransformableAudioFrame>(
      std::move(transformable_frame)));
}
```

Video の `src/sora_frame_transformer.h:325-336` も、`SoraTransformableVideoFrame` を構築する点以外は同じである。

`src/sora_call.h:13-25` の `call_python` は GIL を取得せず、例外のログ出力と再送出だけを行うラッパーである。
現在の frame transformer は `call_python` も使わずに `on_transform_` を直接呼んでいるため、GIL の取得責務は `Transform` にある。

### 呼び出し経路とフレームの所有権

`src/sora_frame_transformer.h:29-57` の `SoraFrameTransformerInterface::Transform` は、受け取った `std::unique_ptr<webrtc::TransformableFrameInterface>` を `SoraTransformFrameCallback::Transform` へ転送するだけである。
この SDK 側の転送処理は mutex を取得しない。

`webrtc::FrameTransformerInterface` は `Transform` と `TransformedFrameCallback::OnTransformedFrame` を別の virtual 関数として定義しており、`Transform` の戻り値で変換済みフレームを返す同期 API ではない。
ただし、現在の SDK は `Transform` の呼び出し中に `on_transform_` を同期的に呼び、callback が同じスタックで `SoraFrameTransformer::Enqueue` を呼ぶ設計である。
この callback の呼び出しスレッド、同期性、`transformable_frame` の所有権を今回変更してはならない。

`SoraFrameTransformer::Enqueue` (`src/sora_frame_transformer.h:184-187`) は `SoraTransformableFrame::ReleaseFrame()` でフレームの所有権を解放し、`SoraFrameTransformerInterface::Enqueue` へ渡す。
callback の外でこのフレームを使えるようにする、または `Transform` から別タスクへ暗黙に移動する変更は行わない。

### 公開 API とライフサイクル

`src/sora_sdk_ext.cpp:575-592` と `src/sora_sdk/sora_sdk_ext.pyi:335-360` で、Audio / Video transformer と `on_transform` が公開されている。
`src/sora_sdk_ext.cpp:150-214` の GC traverse / clear は `on_transform_` を Python callable として扱っているため、`on_transform_` の読み出しと callable 呼び出しは GIL 保持下で行う必要がある。

`SoraFrameTransformer::Del` (`src/sora_frame_transformer.h:177-178`) は `SoraFrameTransformerInterface::ReleaseTransformer` を呼び、以後 `Transform` から SDK オブジェクトへ転送しない状態にする。
今回の修正では `Del`、`ReleaseTransformer`、`Enqueue` のライフサイクルや、未設定の `on_transform_` を呼んだ場合の既存の `std::bad_function_call` 挙動を変更しない。

## 設計方針

### GIL の取得

`src/sora_frame_transformer.h` では、Python.h を nanobind より先に読み込める位置へ `gil.h` を include し、Audio / Video それぞれの `Transform` の先頭で `gil_scoped_acquire acq;` を構築する。
GIL のスコープは `SoraTransformableAudioFrame` または `SoraTransformableVideoFrame` のラッパー構築から `on_transform_` の callback 呼び出しが終わるまで維持する。

実装は次の形にする。

```cpp
void Transform(std::unique_ptr<webrtc::TransformableFrameInterface>
                   transformable_frame) override {
  gil_scoped_acquire acq;
  on_transform_(std::make_unique<SoraTransformableAudioFrame>(
      std::move(transformable_frame)));
}
```

Video も同じ位置で GIL を取得し、ラッパー型だけを `SoraTransformableVideoFrame` にする。
`call_python` への責務移動、`on_transform_` の null チェック追加、callback の例外処理変更は今回行わない。

### ロック、スレッド、終了処理

SDK 側の `Transform` から Python callback までの経路には mutex がなく、既存の video sink のように `Transform` 本体をタスクキューへ送る必要はない。
`PostTask`、専用タスクキュー、callback 待ち用の join、フレームの共有所有権化は導入しない。
これにより、既存の callback の同期的な呼び出し、callback 内での `enqueue`、フレームの借用期間を維持する。

実装時には `SoraFrameTransformerInterface::Transform`、Audio / Video の sender / receiver 設定経路、`Enqueue`、`ReleaseTransformer` を確認し、今回追加する GIL と SDK 側 mutex の逆順取得を作らないことをコードレビューで確認する。
Python callback からの同期的な接続切断、transformer 破棄、`on_transform` の再設定は既存の再入・ライフサイクル制約であり、今回の変更で新しい非同期動作を導入しないことを確認する。

`gil_scoped_acquire` の Python 終了処理時のメンバ初期化問題は `issues/0057-bug-fix-gil-scope-uninitialized-member.md` の対象である。
0019 の実装は 0057 の修正を先に develop へ取り込んだ状態を前提とし、`src/gil.h` の別修正を 0019 に重複して含めない。
通常のライフサイクルでも、Python インタプリタの終了前に Sora の接続、track、frame transformer を破棄して、Python callback が終了処理中に発火しないことを保証する。

### テスト方針

モックやスタブは使用せず、既存の実接続 E2E テスト `tests/test_encoded_transform.py` を拡張する。

- 送信側 Audio / Video と受信側 Audio / Video の 4 経路それぞれで、`on_transform` callback の発火を `threading.Event` で通知する。
- callback 内では `get_data()`、NumPy によるデータ加工、`set_data()`、`enqueue()` を実行し、GIL 保持が必要な nanobind / Python / NumPy の処理を実際に通過させる。
- callback 内で `assert` を送出しない。callback 内で発生した例外は `try` / `except` で保存し、`finally` でイベントを設定して callback を戻し、テストスレッド側でイベント待機後に例外内容を検証する。native スレッド上の未処理例外でプロセスを終了させない。
- テストスレッドで各イベントを timeout 付きで待ち、Audio / Video の全経路が発火したこと、保存した callback 例外がないこと、各 callback がテストスレッド以外から実行されたことを確認する。
- 受信側 callback で送信側が付加したデータを検証する場合も callback 内で assert せず、検証結果を保存してテストスレッド側で確認する。
- イベント待機と callback の結果確認を切断前に完了させ、切断後に worker thread が Python callback を継続しないことを確認する。
- 既存の `tests/test_encoded_transform.py` の codec / RTP stats 検証を維持し、イベント待機で callback 発火を確認した後に stats を取得する。固定時間の `sleep` だけを callback 発火の根拠にしない。

Python のテストだけでは GIL の保持状態そのものを証明できないため、実接続テストで対象経路と Python 処理の発火を確認し、`src/sora_frame_transformer.h` の実装で `gil_scoped_acquire` が callback より前にあることを確認する。

## 変更対象

- `src/sora_frame_transformer.h`: `gil.h` の include と Audio / Video の `Transform` での GIL 取得。
- `tests/test_encoded_transform.py`: Audio / Video の送受信 callback を timeout 付き Event と結果保存で検証する。
- `CHANGES.md`: `## develop` に担当者行付きの `[FIX]` エントリを追加する。

`src/sora_frame_transformer.cpp` は存在しないため変更しない。
`src/sora_sdk_ext.cpp`、`src/sora_sdk/sora_sdk_ext.pyi`、公開 API のシグネチャは変更しない。

## 完了条件

- Audio / Video 両方の `Transform` が `gil_scoped_acquire` を `on_transform_` 呼び出しより前に構築し、ラッパー構築から callback 終了まで GIL を保持すること。
- Audio / Video の送信側・受信側の 4 経路で、`get_data()`、`set_data()`、`enqueue()` を含む実接続 callback が発火し、テストスレッド側で結果を検証できること。
- callback の呼び出しスレッド、同期的な呼び出し方、フレーム所有権、`on_transform_` 未設定時の既存挙動が変わらないこと。
- `Transform` 経路に新しい SDK 側 mutex の逆順取得、`PostTask`、専用タスクキュー、join 待ちを導入しないこと。
- Python 終了前に接続、track、frame transformer を破棄する既存ライフサイクルを確認し、0057 の修正を先行依存として扱うこと。
- `tests/test_encoded_transform.py` の既存 codec / RTP stats 検証を含むテストが通ること。
- 既存の全体ビルド・テストが通ること。
- `CHANGES.md` の `## develop` に、`[FIX]` の種別順と担当者行の書式を満たすエントリを追加すること。
- 実装完了時に `Completed: YYYY-MM-DD` を追加し、`## 解決方法` に変更内容、GIL を取得する位置、テスト結果、0057 との依存解消を記録すること。

## 後方互換性

Python 公開 API、`on_transform` の引数型、callback の同期的な呼び出し方、`enqueue` によるフレーム返却方法は変更しない。
変更されるのは、libwebrtc の worker thread から Python callback を実行する前に GIL を取得する点だけである。

## 関連 issue

- `issues/0057-bug-fix-gil-scope-uninitialized-member.md`: `gil_scoped_acquire` / `gil_scoped_release` のメンバ未初期化による UB。0019 は 0057 の修正を先行依存とする。
- `issues/0018-bug-fix-audio-on-data-missing-gil.md`: 音声 sink callback の GIL 未取得。対象は audio sink であり、frame transformer の `Transform` とは対象シンボルが重複しない。
- `issues/closed/0009-bug-fix-on-push-missing-gil.md`: native thread から Python callback を呼ぶ前に GIL を取得した先例。
- `issues/closed/0012-bug-fix-audio-sink-read-holds-gil.md`: GIL と SDK mutex のロック順序を確認した先例。
- `issues/closed/0014-bug-fix-read-pyerr-checksignals-not-propagated.md`: GIL を扱う音声経路の例外伝播を確認した先例。

## 参照

- [WebRTC `FrameTransformerInterface`](https://webrtc.googlesource.com/src/+/refs/heads/main/api/frame_transformer_interface.h): `Transform` と `TransformedFrameCallback::OnTransformedFrame` を別 API として定義している。
- [WebRTC Encoded Transform](https://www.w3.org/TR/webrtc-encoded-transform/): sender / receiver の encoded frame を transform して返す仕様。
