# サイマルキャスト最小解像度層の targetBitrate 閾値割れにより flaky に失敗する問題を修正する

- Priority: Low
- Created: 2026-06-05
- Model: Opus 4.8
- Branch: feature/fix-flaky-simulcast-target-bitrate
- Polished: 2026-07-28

## 目的

CI の e2e-test で `tests/test_authz_simulcast.py::test_authz_simulcast_r2_and_r1_active_false[VP8-libvpx-240-135]` が flaky に失敗した。11 プラットフォーム中 `ubuntu-22.04_armv8` の 1 つのみが失敗し、同一アーキの `ubuntu-24.04_armv8` を含む他は全て成功している。

- CI run: https://github.com/shiguredo/sora-python-sdk/actions/runs/26993739301/job/79659113836 (develop への push でトリガー)
- 失敗内容: `AssertionError: assert 30000 >= 45000.0` (`45000.0 = expect_target_bitrate('VP8', 240, 128)`)
- 結果サマリ: `1 failed, 73 passed, 85 skipped, 1 xfailed`

この flaky 失敗の構造的原因を解消し、CI を安定させる。

## 優先度根拠

Low とする。

- 製品コードのバグではなく、テスト側の期待値 (閾値) の構造的なミスキャリブレーションであり、メモリ破壊やクラッシュ等の実害は無い。
- 再現は低頻度。11 環境中 1 環境のみで、低速・制約のある ARM ランナー (`ubuntu-22.04_armv8`) のビットレート立ち上がり遅延に依存する。再実行すれば通ることが多い。
- ただし flaky 失敗は CI を赤くしてマージを妨げ、再実行の常態化が本物の失敗を覆い隠す副作用があるため放置はしない。頻度が上がるようなら優先度を見直す。

## 現状

### 失敗するアサーション

`tests/test_authz_simulcast.py` の 300-302 行:

```python
assert s["targetBitrate"] >= expect_target_bitrate(
    video_codec_type, s["frameWidth"], s["frameHeight"]
)
```

直前の 293-294 行に `qualityLimitationReason != "none"` なら `pytest.skip` する緩衝策があるが、今回は `reason == "none"` だったため skip されずに失敗した。

### パラメータ

失敗ケースは parametrize の `("VP8", "libvpx", 240, 135)`。`r0` のみ active で `r1` / `r2` は inactive (最小解像度の単一レイヤー)。JWT で要求する `video_bit_rate` は `default_video_bit_rate("VP8", 240, 135) = 130` kbps。`time.sleep(10)` 後に統計を取得する。統計上のフレーム (`frameWidth` x `frameHeight`) は 240x128 だった (高さがエンコーダのアライメントで 135 → 128 に調整されたとみられる)。

### 根本原因

`tests/simulcast.py` の `expect_target_bitrate` は次のとおり:

```
expect_target_bitrate = simulcast_format(codec, w, h) * 1000 * MIN_TARGET_BITRATE_RATIO   (= 0.3)
```

- VP8 / 240x128 では `simulcast_format_vp8` が `240*128 = 30720 <= 240*135 = 32400` の分岐に入り `150` を返す。これは 320x180 の target 値 (150 kbps) をそのまま流用した仮定値であり、240x135 は 320x180 よりピクセル数が約 44% 少なく補間領域 (target → 0 へ収束) にあるため、過大推定になっている。
- よって期待床 = `150 * 1000 * 0.3 = 45000`。
- 一方 WebRTC の VP8 サイマルキャストテーブル (`simulcast.py` の docstring に転記されている `kSimulcastFormatsVP8`) では、320x180 の target は 150 kbps、{0,0} の target は 0 kbps で、その間は線形補間される。240x135 のピクセル数 32400 は 320x180 の 57600 の約 56% であり、補間による steady-state target は約 84 kbps と推定される。min の 30 kbps 床はキャップとして存在するが、84 > 30 なので通常は発動しない。
- 実測 `targetBitrate = 30000` は、低速な ARM ランナー (`ubuntu-22.04_armv8`) で 10 秒以内にビットレートのランプアップが完了しなかった過渡値である可能性が高い。1/11 環境のみ失敗し他環境では成功するという事実は、timing が主因であることを示唆する。
- ただし「テストが仮定した期待床 45000」が「補間による steady-state 約 84000」の 30% (= 25200) ではなく、320x180 の target をそのまま使った過大値であることも事実であり、閾値自体のミスキャリブレーションと timing の両方が flaky に寄与している。

### VP9 / AV1 240x135 の同種リスク

`simulcast_format_vp9(240, 135)` は `101` を返すため:

- 期待床 = `101 * 1000 * 0.3 = 30300`
- WebRTC の VP9 テーブルで 240x135 の min = 30 kbps = `30000`
- マージンはわずか 300 bps (1%) であり、エンコーダが min 床に張り付けば `30000 < 30300` で同様に失敗する

AV1 も `simulcast_format_vp9` を使うため同様。テストの parametrize には `("VP9", "libvpx", 240, 135)` と `("AV1", "libaom", 240, 135)` が含まれている。

既存の緩衝策 (`MIN_TARGET_BITRATE_RATIO = 0.3` と `qualityLimitationReason` skip) では、これらの最小解像度ケースは拾えていない。

## 設計方針

閾値のミスキャリブレーションと timing の両方に対処する。実装時に以下の候補から選定する (本 issue では断定しない):

1. 最小解像度層の `expect_target_bitrate` を WebRTC の補間テーブルの実態に整合させる。`simulcast_format_vp8` が 240x135 で 320x180 の target 値 (150) を流用している箇所を、補間による実効値に合わせる。ただし VP9 / AV1 は WebRTC テーブルに `{240, 135, target=101}` が明示的に定義されており、`simulcast_format_vp9` の返り値 101 はテーブルと一致している。VP9 / AV1 の問題は期待床 30300 と min 床 30000 のマージンが 300 bps (1%) しかないことであるため、候補 1 単独では VP9 / AV1 を解決できない。VP9 / AV1 には候補 3 (ratio 緩和) または候補 4 (ポーリング) の併用が必要。
2. `targetBitrate` が WebRTC の最小床 (30000) 以下に張り付いているケースを、`qualityLimitationReason` skip の隣で skip 条件に加える。
3. `MIN_TARGET_BITRATE_RATIO` を最小解像度層だけ緩める。
4. `time.sleep(10)` 後の固定 1 回取得を、targetBitrate が期待値に達するまでポーリングする方式に変える (issue 0038 と共通するアプローチ)。ポーリングには最大待機時間 (例: 30 秒) を設け、タイムアウト時は `pytest.skip` で逃がす (帯域推定が min 床に収束した steady-state の場合、永遠に期待値に達しないため)。

候補 2 は検証強度を下げるため、完了条件「検証強度を不必要に緩めない」との整合に注意する。候補 3 も ratio を下げすぎると (例: 0.25 以下) 期待床が min 床を下回りアサーションが自明に真になるトレードオフがある。候補 4 のタイムアウト skip も、min 床に収束した場合は常に skip となり実質的に検証されない。VP8 には候補 1 単独で十分である (候補 1 適用後の期待床は約 25200 となり、WebRTC の min 床 30000 が常にこれを上回るため、タイミングに依存せず閾値割れしない)。VP9 / AV1 には候補 3 (ratio 緩和) または候補 4 (ポーリング + タイムアウト skip) が必須。候補 2 は補助的に使うことを推奨する。

### issue 0038 との関係

issue 0038 (`0038-refactor-replace-time-sleep-with-polling`) は `tests/` 配下の `time.sleep()` をポーリングに置換するリファクタリングであり、`test_authz_simulcast.py:235` の `time.sleep(10)` もその対象に該当する。0038 が先に実装された場合、timing 側の flaky トリガー構造が変わるため、本 issue の候補 4 は不要になる。VP8 は候補 1 単独で解決し、VP9 / AV1 も 0038 のポーリングが候補 4 を代替するため、閾値の補正 (候補 1) と 0038 のポーリングだけで十分になる可能性がある。0038 とは独立に実装可能だが、0038 実装後に本 issue の設計を再評価すること。

## 完了条件

- `test_authz_simulcast_r2_and_r1_active_false` の 240x135 ケース (VP8 / VP9 / AV1) と、`test_authz_simulcast_r2_active_false` の 270p ケース (r0 が `scaleResolutionDownBy: 2` で 240x135 に縮小される) が、エンコーダが低ビットレートに張り付いた場合でも誤って fail しないこと。
- 他の解像度・コーデックのケースの検証強度を不必要に緩めないこと。
- 修正の根拠 (WebRTC の補間テーブルと、テストの期待値の関係) をコメント等で明確にすること。
- CI の e2e-test が安定して通ること。
