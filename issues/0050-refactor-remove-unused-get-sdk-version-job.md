# `get_sdk_version` ジョブが他から参照されていない死コードを整理する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-remove-unused-get-sdk-version-job
- Polished: 2026-07-30

## 目的

`.github/workflows/build.yml` の `get_sdk_version` ジョブは `outputs.sdk_version` を出力するために定義されているが、同ワークフロー内の他のジョブからは `needs: [get_sdk_version]` も `${{ needs.get_sdk_version.outputs.sdk_version }}` も一切参照されていない。
結果として、push のたびに何も使われないジョブが起動し、CI の実行時間とコストを無駄に消費している。
本 issue では当ジョブを削除し、無参照のまま動き続ける状態を解消することを目的とする。

## 優先度根拠

Medium とする。

- ビルド自体は問題なく動いており、機能的なバグではない。しかし CI の毎回の実行で無駄なジョブが回ること自体が「壊れた窓」であり、放置すると同種のデッドコードが他にも増殖する。Don't live with broken windows の観点から無視できない。
- 削除は最小変更でリスクが低いため Medium。

## 現状

`.github/workflows/build.yml` の `get_sdk_version` ジョブ:

```yaml
  get_sdk_version:
    runs-on: ubuntu-slim
    outputs:
      sdk_version: ${{ steps.version.outputs.sdk_version }}
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
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

- `build.yml` から `get_sdk_version` ジョブの定義を削除する。
- 既存のビルドジョブは個別に `VERSION` を読んでおり、`get_sdk_version` の出力を参照していないため、削除による影響範囲は無い。
- 将来的に Release のタイトル整合性チェック等で `sdk_version` 出力が必要になった場合は、その時点で別 issue として起票する。

## 完了条件

- `build.yml` から `get_sdk_version` ジョブが削除されていること。
- 既存ジョブが従来どおり成功すること (push / tag push 双方で build.yml が成功すること)。
- CI 実行時間が短縮されること (ジョブ 1 つ分の起動がなくなること)。
