# サイマルキャスト最小解像度の VP8 で test_authz_simulcast_r2_and_r1_active_false が targetBitrate 閾値割れにより flaky に失敗する問題を修正する

- Priority: Low
- Created: 2026-06-05
- Model: Opus 4.8
- Branch: feature/fix-flaky-simulcast-target-bitrate

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

- VP8 / 240x128 では `simulcast_format_vp8` が `240*128 = 30720 <= 240*135 = 32400` の分岐に入り `150` を返す。これは `simulcast.py` のコメント「vp8 では 240x135 は未定義なので 150 と仮定する」による仮定値。
- よって期待床 = `150 * 1000 * 0.3 = 45000`。
- 一方 WebRTC の VP8 サイマルキャストテーブル (`simulcast.py` の docstring に転記されている `kSimulcastFormatsVP8`) では、最小解像度のハード下限ビットレートは 30 kbps で、低解像度では target / max が 0 に向けて補間されつつ min 30 kbps で下支えされる。実測 `targetBitrate = 30000` はこの 30 kbps 床に張り付いた値。
- つまり「テストが仮定した VP8 240x135 の期待床 45000」が「WebRTC が実際に出す下限 30000」を上回っており、エンコーダが床に落ち着くと構造的に閾値割れする。低速な ARM ランナーでビットレートが立ち上がりきらないと再現し、他環境では立ち上がって通る。これが「1 / 11 環境のみ失敗・同一アーキ別 OS は成功」という flaky の症状として現れている。

既存の緩衝策 (`MIN_TARGET_BITRATE_RATIO = 0.3` と `qualityLimitationReason` skip) では、この最小解像度 VP8 の床割れケースは拾えていない。

## 設計方針

「テストが仮定する期待床が WebRTC のハード下限 (30 kbps) を上回る」状態を解消する。実装時に以下の候補から選定する (本 issue では断定しない):

1. 最小解像度層の `expect_target_bitrate` を WebRTC の下限 (30 kbps) に整合させる。`simulcast_format_vp8` が 240x135 で `150` を仮定している箇所を、WebRTC の補間 + 30 kbps 床の実態に合わせる。
2. `targetBitrate` が WebRTC の最小床 (30000) 付近に張り付いているケースを、`qualityLimitationReason` skip の隣で skip 条件に加える。
3. `MIN_TARGET_BITRATE_RATIO` を最小解像度層だけ緩める。

VP8 だけでなく、他コーデック・他解像度で同種の床割れが起きないかも併せて確認する。

## 完了条件

- `test_authz_simulcast_r2_and_r1_active_false[VP8-libvpx-240-135]` が、エンコーダが 30 kbps 床に張り付いた場合でも誤って fail しないこと。
- 他の解像度・コーデックのケースの検証強度を不必要に緩めないこと。
- 修正の根拠 (WebRTC の最小ビットレート床と、テストの期待値の関係) をコメント等で明確にすること。
- CI の e2e-test が安定して通ること。
