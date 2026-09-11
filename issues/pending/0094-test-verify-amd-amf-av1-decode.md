# Ubuntu の AMD AMF で AV1 デコードが動作するかを定期的に確認する

- Created: 2026-09-11
- Completed: -
- Branch: feature/test-verify-amd-amf-av1-decode
- Polished: -
- Reporter: @sile

## 目的

Ubuntu x86_64 の AMD AMF で AV1 デコードが動作するようになったかを定期的に確認できるようにする。

現状は AV1 デコードが動作しない前提でテストに TODO が残ったままになっており、AMD のドライバーや AMF / libwebrtc の更新で状況が変わる可能性がある。動作するようになった時点で検知し、テストと README と変更履歴へ反映する。

## 現状

- `tests/test_amd_amf.py` の `test_amd_amf_available` は AV1 について `c.decoder is True` と `c.encoder is True` を assert しており、直前に `# TODO: AV1 decoder は True だが色々課題あり` というコメントがある。
- `tests/test_amd_amf.py` の `test_amd_amf_sendonly_recvonly` は AV1 / H264 / H265 を parameterize し、recvonly 側の `decoderImplementation == "AMF"` と `keyFramesDecoded > 0` を assert する。AV1 の AMF デコードを実行時に検証する唯一のテストだが、AMD AMF の E2E が無効なため実行されていない。
- AV1 のデコードだけを確認する専用テストは無い。Intel VPL は `tests/test_intel_vpl.py` の `test_intel_vpl_decode` で AV1 のソフトウェアエンコードとハードウェアデコードの組み合わせを検証している。
- `README.md` の AMD AMF の制約は `AV1 エンコードは Windows x86_64 でのみ利用できる` と `VP9 はデコードのみ利用できる` だけで、AV1 デコードの Ubuntu 制約には触れていない。
- `.github/workflows/e2e-test.yml` の AMD AMF の matrix entry (`[self-hosted, linux, x64, AMD-AMF]`) はコメントアウトされている。`e2e-test.yml` 自身の `on.schedule` もコメントアウトされているが、`.github/workflows/build.yml` の平日の `on.schedule` が `e2e_test` job 経由で `e2e-test.yml` を呼ぶため、平日の定期 E2E は AMD AMF を除いて動作している。
- 過去に `.github/workflows/e2e-test-amd-amf.yml` が存在し、`on.schedule` 付きで AMD AMF の E2E を定期実行していた。このワークフローは統合で削除され、AMD AMF entry はコメントアウトされた。
- `CHANGES.md` には AMD AMF の Ubuntu / Windows 対応と E2E テスト追加の記載はあるが、AV1 デコードの Ubuntu 制約の記載は無い。
- Ubuntu の AMD AMF で AV1 デコードが動作しない理由 (AMF SDK / AMD ドライバー / libwebrtc のどの層の制約か) はリポジトリ内に記録されていない。

## 設計方針

保留を解除したら、まず定期的な確認の実現方法を決める。候補は次のとおり。

- `.github/workflows/build.yml` の平日 schedule 経由で動く `e2e-test.yml` の AMD AMF matrix entry を有効化し、`tests/test_amd_amf.py` を定期実行する。
- AV1 デコードだけを確認する専用テストを追加する。`tests/test_intel_vpl.py` の `test_intel_vpl_decode` と同様に、ソフトウェアエンコードと AMD AMF デコードの組み合わせで `decoderImplementation == "AMF"` を確認する。

あわせて次の点を整理する。

- AV1 デコードが動作しない原因を切り分け、どの層の制約かをリポジトリ内に記録する。
- 動作しない間は fail ではなく skip / xfail として扱い、動作するようになったら通常テストとして通す。
- 確認結果を `README.md` の AMD AMF の対応表記と `CHANGES.md` に反映する。Sora C++ SDK の `doc/known_issues.md` / `doc/faq.md` との整合も確認する。

## 完了条件

- Ubuntu x86_64 の AMD AMF で AV1 デコードが動作するかを定期実行で確認できる。
- 動作しない場合、その理由と確認手順がリポジトリ内に記録されている。
- 動作するようになった場合、`tests/test_amd_amf.py` の TODO と `README.md` の AMD AMF の対応表記と `CHANGES.md` が更新されている。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- Ubuntu の AMD AMF で AV1 デコードが動作しない理由 (どの層の制約か、「仕様」の出典) がリポジトリ内に記録されていない。
- 定期的な確認の実現方法 (スケジュール CI の復活か、専用テストの追加か) が未確定。
- AMD AMF 用 self-hosted runner の現状 (ラベル、AMD ドライバーのバージョン、利用可否) が不明。
- 元になった報告は社内のリンクのみで、前提をリポジトリ内で確認できない。

再開するときは reopened にしてから実装を進める。
