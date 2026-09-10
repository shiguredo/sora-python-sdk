# nanobind で引数名を指定していない箇所の help / pyi の arg0・arg を解消する

- Created: 2026-09-10
- Completed: -
- Branch: feature/change-nanobind-argument-names
- Polished: -

## 目的

nanobind はバインディング時に `nb::arg("name")` または `"name"_a` で引数名を指定しないと、`help()` やビルド時に生成される型スタブ (`sora_sdk_ext.pyi`) で引数が `arg` または `arg0` / `arg1` として表示される。利用者はエディタ補完や `help()` から引数の意味を読み取れず、キーワード引数も使えない。

2023 年に `SoraAudioSource.on_data` / `SoraVideoSource.on_captured` / `SoraVAD.analyze` へ PR #35 で引数名を付けたが、その後に追加された関数と `def_rw` の setter には引数名未指定が残り、同じ問題が再発している。本 issue で全箇所に名前を付けて解消する。

## 現状

`src/sora_sdk_ext.cpp` の nanobind バインディングに、引数名を渡していない箇所が残っている。リリース済み `sora-sdk 2026.1.0` の wheel を展開し、生成された `sora_sdk_ext.pyi` で確認した未指定箇所は次のとおり。

### 関数・メソッド

| シンボル | 生成 pyi での表示 | 付与する名前 |
| --- | --- | --- |
| `EnableLibwebrtcLog` | `enable_libwebrtc_log(arg)` | `severity` |
| `RtcLog` | `rtc_log(arg0, arg1)` | `severity`, `message` |
| `SoraMediaTrack::SetFrameTransformer` | `set_frame_transformer(self, arg)` | `transformer` |
| `SoraTransformableFrame::SetData` | `set_data(self, arg)` | `data` |
| `SoraFrameTransformer::Enqueue` | `enqueue(self, arg)` | `frame` |
| `sora::VideoCodecPreference::Find` のバインディング lambda | `find(self, arg)` | `type` |
| `sora::VideoCodecPreference::GetOrAdd` のバインディング lambda | `get_or_add(self, arg)` | `type` |
| `sora::VideoCodecPreference::HasImplementation` | `has_implementation(self, arg)` | `implementation` |
| `sora::VideoCodecPreference::Merge` | `merge(self, arg)` | `preference` |
| `sora::CreateVideoCodecPreferenceFromImplementation` | `create_video_codec_preference_from_implementation(arg0, arg1)` | `capability`, `implementation` |
| `SoraVideoSinkImpl` の `nb::init<SoraTrackInterface*>` | `__init__(self, arg)` | `track` |
| `SoraAudioFrame` の `__setstate__` lambda | `__setstate__(self, arg)` | `state` |

`Find` / `GetOrAdd` のバインディングは lambda の第 1 引数が `self` になるため、`nb::arg` は第 2 引数にのみ付与する。

### `def_rw` / `def_prop_rw` の setter

property setter の値引数が `arg` として表示される。

- `SoraAudioSinkImpl` の `on_data`, `on_format`
- `SoraAudioStreamSinkImpl` の `on_frame`
- `SoraVideoSinkImpl` の `on_frame`
- `SoraConnection` の `on_set_offer`, `on_ws_close`, `on_disconnect`, `on_signaling_message`, `on_notify`, `on_push`, `on_message`, `on_rpc`, `on_switched`, `on_track`, `on_data_channel`
- `SoraTransformableFrame` の `rtp_timestamp`
- `SoraAudioFrameTransformer` / `SoraVideoFrameTransformer` の `on_transform`
- `sora::VideoCodecPreference` の `codecs`
- `sora::VideoCodecPreference::Codec` の `type`, `encoder`, `decoder`, `parameters`

## 設計方針

- nanobind の `nb::arg("name")` / `"name"_a` を未指定箇所すべてに付与する。名前は C++ 側の引数名に合わせる (PR #35 の方針)。
- lambda を `.def` する箇所もメソッドと同様に扱い、`self` 以外の引数に `_a` を付与する。
- `nb::init<...>` にも `"track"_a` を付与する。
- `def_rw` / `def_prop_rw` の setter は `nb::for_setter(nb::arg("value"))` を使う。`def_rw` は受け取った Extra を `def_prop_rw` 経由で setter の `cpp_function` に転送するため、setter の値引数にだけ名前を付けられる。`on_*` のコールバック property は意味が分かるよう `callback`、それ以外は `value` とする。
- nanobind 3.0.0 / 3.0.1 でも引数名未指定時は `arg` / `arg{index}` を生成する実装のままであることを nanobind の `src/nb_func.cpp` で確認済み。バージョンアップでは解決しないため、明示的に名前を付ける。
- 引数名の付与は位置引数呼び出しを壊さず、キーワード引数を可能にする変更である。CHANGES.md では既存の引数名変更 (PR #35) と同じ `[CHANGE]` として記載する。

## 完了条件

- `src/sora_sdk_ext.cpp` のバインディングで引数名未指定箇所が残っていないこと。
- ビルド時に生成される `sora_sdk_ext.pyi` に `arg0` / `arg1` が含まれないこと。
- `sora_sdk_ext.pyi` の公開関数・メソッド・property setter に、今回のバインディングに由来する `arg` が含まれないこと。
- 既存のテストが通り、wheel ビルドが成功すること。
- CHANGES.md にエントリが追記されていること。

## 解決方法

1. `src/sora_sdk_ext.cpp` の該当する `.def` / `.def_rw` / `.def_prop_rw` / `nb::init` に `_a` を追加する。モジュール関数は `m.def` に `nb::arg` を追加する。
2. wheel をビルドし、生成された `sora_sdk/sora_sdk_ext.pyi` を展開して `arg0` / `arg1` / `arg` が残っていないことを確認する。
3. CHANGES.md の `## develop` に追記する。
