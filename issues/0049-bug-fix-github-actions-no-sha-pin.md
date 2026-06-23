# `shiguredo/github-actions/*@main` の SHA pin 化を行う

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-github-actions-no-sha-pin

## 目的

`.github/workflows/build.yml` および `.github/workflows/e2e-test.yml` で利用している社内アクション `shiguredo/github-actions/.github/actions/*` だけが `@main` ブランチを直接参照している。
他のサードパーティアクション (`actions/checkout`、`actions/upload-artifact`、`astral-sh/setup-uv`、`pypa/gh-action-pypi-publish` など) はすべて 40 桁の commit SHA で pin され、コメントでバージョン番号を併記している。
社内アクションだけ `@main` を参照していると、`shiguredo/github-actions` 側の `main` ブランチで破壊的変更が入った瞬間に Sora Python SDK の CI が突然壊れる。再現が「ある日突然」になるため復旧コストも高い。
本 issue では社内アクションも SHA pin に切り替え、CI の再現性と安定性を確保することを目的とする。

## 優先度根拠

Medium とする。

- 外部依存 (サードパーティ) は既に SHA pin で揃っており、社内依存だけ抜けている整合性欠落である。サプライチェーン上のリスクは低いが、CI の再現性 (今日通ったコードが明日も通る) を担保するには pin が必要。
- 一方、`shiguredo/github-actions` は時雨堂内のコントロール下にあり外部の悪意ある変更リスクは小さいため、High ではなく Medium。

## 現状

該当箇所は以下のとおり (パスと行は実装時に再確認する)。

- `.github/workflows/build.yml`:
  - 335 行: `uses: shiguredo/github-actions/.github/actions/slack-notify@main # main`
  - 397 行: `uses: shiguredo/github-actions/.github/actions/slack-notify@main # main`
  - 497 行: `uses: shiguredo/github-actions/.github/actions/slack-notify@main # main`
- `.github/workflows/e2e-test.yml`:
  - 198 行: `uses: shiguredo/github-actions/.github/actions/download-openh264@main # main`
  - 253 行付近: `uses: shiguredo/github-actions/.github/actions/slack-notify@main # main`

他のアクションは以下のように pin されている (例)。

```yaml
- uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
- uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
- uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0
```

社内アクションだけが `@main` のままになっており、pin の方針が CI 全体で揃っていない。

## 設計方針

- `shiguredo/github-actions` リポジトリ側で `slack-notify` / `download-openh264` の安定版 tag を切る運用にし、その tag に対応する 40 桁の commit SHA を `@<sha> # <tag>` の形式で pin する。
- 既に該当アクションが tag 切られているなら、現状の `main` HEAD に近い tag を採用する。
- pin に切り替える際は、機能差分を確認 (`slack-notify` の入力パラメータ、`download-openh264` の出力など) し、ワークフロー側で参照しているインタフェースが互換であることを担保する。
- 将来の更新運用 (Dependabot 等で SHA を更新できるようにするか) は別 issue で扱うことができる。本 issue は「現在の `@main` 参照を SHA pin に置き換える」一段の作業とする。

## 完了条件

- `.github/workflows/build.yml` および `.github/workflows/e2e-test.yml` 内の `shiguredo/github-actions/*@main` 参照がすべて `@<40 桁 SHA> # <tag>` 形式に置き換わっていること。
- pin した SHA が対応する tag を確かに指しており、ワークフローが従来どおり成功すること (CI 上で動作確認)。
- `shiguredo/github-actions` 側に必要な tag が無い場合は、tag を切る運用への切り替えが合意されていること (合意先は別途記録する)。
- pin 後の CI が build / e2e-test の両方で通ること。
