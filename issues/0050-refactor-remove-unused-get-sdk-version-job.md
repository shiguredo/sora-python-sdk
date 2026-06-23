# `get_sdk_version` ジョブが他から参照されていない死コードを整理する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/remove-unused-get-sdk-version-job

## 目的

`.github/workflows/build.yml` の `get_sdk_version` ジョブは `outputs.sdk_version` を出力するために定義されているが、同ワークフロー内の他のジョブからは `needs: [get_sdk_version]` も `${{ needs.get_sdk_version.outputs.sdk_version }}` も一切参照されていない。
結果として、push のたびに何も使われないジョブが起動し、CI の実行時間とコストを無駄に消費している。
本 issue では、当ジョブを「使う」もしくは「消す」のどちらかに整理し、無参照のまま動き続ける状態を解消することを目的とする。

## 優先度根拠

Medium とする。

- ビルド自体は問題なく動いており、機能的なバグではない。しかし CI の毎回の実行で無駄なジョブが回ること自体が「壊れた窓」であり、放置すると同種のデッドコードが他にも増殖する。Don't live with broken windows の観点から無視できない。
- 利用方法 (publish_wheel / create-release のいずれかで活用するか、純粋に削除するか) を要設計判断のため High ではなく Medium。

## 現状

`.github/workflows/build.yml` の 31-47 行:

```yaml
jobs:
  # VERSION ファイルからバージョン情報を取得
  get_sdk_version:
    runs-on: ubuntu-slim
    outputs:
      sdk_version: ${{ steps.version.outputs.sdk_version }}
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          sparse-checkout: |
            VERSION
          sparse-checkout-cone-mode: false
      - id: version
        run: |
          SDK_VERSION=$(cat VERSION)
          echo "sdk_version=$SDK_VERSION" >> $GITHUB_OUTPUT
          echo "SDK Version: $SDK_VERSION"
```

このジョブは:

- `VERSION` ファイルを sparse-checkout し、その内容を `sdk_version` 出力として公開する。
- しかし `build.yml` 内の他ジョブ (`build_pyi` / `build_ubuntu` / `build_ubuntu_arm` / `build_macos` / `build_windows` / `slack_notify` / `e2e_test` / `publish_wheel` / `create-release`) のいずれにも `needs: [get_sdk_version]` 記述は無く、`${{ needs.get_sdk_version.outputs.sdk_version }}` の参照も無い。
- 各ビルドジョブはそれぞれ `cat VERSION` 相当を独自に行っており、`get_sdk_version` の出力を必要としていない。

push / tag push 時に毎回起動するが何にも繋がっていない、純粋な無参照ジョブになっている。

## 設計方針

以下のいずれかを採用する。本 issue では結論を断定しない。

1. ジョブを削除する。
   - 既存のビルドジョブは個別に `VERSION` を読んでおり、影響範囲は無い。
   - 最小変更で死コードを排除できる。
2. `publish_wheel` / `create-release` から `needs: [get_sdk_version]` で参照し、Release のタイトル・artifact 命名・ログ表示などに活用する。
   - Release タイトルは現在 `${{ github.ref_name }}` を使っているため、`sdk_version` を使う意味があるかは要検討。
   - 利用するなら、`VERSION` を tag 名と二重管理しないよう、整合性チェックを兼ねた使い方が望ましい (例: `${{ github.ref_name }}` と `sdk_version` が一致することを検証する step を追加するなど)。

判断は実装時に行う。最小変更案としては 1 (削除) が妥当だが、Release のタイトル整合性チェックは導入価値があるため 2 も検討する。

## 完了条件

- `get_sdk_version` ジョブが「削除」もしくは「他ジョブから参照される形」になっていること (どちらに転んでも、無参照のまま動き続ける状態を解消する)。
- 削除する場合: 既存ジョブが従来どおり成功すること。CI 実行時間が短縮されること。
- 残して参照する場合: `needs: [get_sdk_version]` を追加した先のジョブが、参照を含む形で正しく動作すること。Release のタイトルや artifact 命名で `sdk_version` を活用する場合、その挙動が期待通りであること。
- どちらの方針でも、push / tag push 双方で build.yml が成功すること。
