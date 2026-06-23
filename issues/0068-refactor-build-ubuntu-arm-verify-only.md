# build_ubuntu_arm を「検証専用ジョブ」として明示するか native arm wheel 配布に切り替える

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/refactor-build-ubuntu-arm-verify-only

## 目的

`.github/workflows/build.yml` の `build_ubuntu_arm` ジョブは、native arm ランナー (`ubuntu-24.04-arm` / `ubuntu-22.04-arm`) 上で `ubuntu-24.04_armv8` / `ubuntu-22.04_armv8` の 2 ターゲット x Python 3.12 / 3.13 / 3.14 の合計 6 種類のビルドを実行する。
しかし `actions/upload-artifact` を一切呼んでおらず、生成された wheel は CI 終了とともに破棄される。
一方で同じ wheel は `build_ubuntu` (x86_64 ランナーから multistrap でクロスビルド) でも作られて upload されており、`publish_wheel` / `create-release` はそちらを使う。

すなわち `build_ubuntu_arm` は「クロスビルド結果と一致するかを native arm で再ビルド検証する」役割を果たしているのに、コード上では普通のビルドジョブと区別できず、CI 時間を浪費しているように見える。

実態としては `slack_notify.needs` に含まれているため失敗通知は飛ぶが、その意図が CI 設定の表面からは読み取れない。これを是正する。

## 優先度根拠

Medium とする。

- 現状の CI は動いており、`build_ubuntu_arm` の失敗通知は機能している (Slack に上がる)。
- ただし「artifact を上げないビルドジョブが 6 個ある」のは新規メンバーから見ると重複ビルドにしか見えず、削除候補に挙がる危険がある。実際には削るとクロスビルド結果の native 検証が消えるため、構造的に保護すべき意図がある。
- CI 時間も `build_ubuntu_arm` 単体で 15 分 x 6 ジョブ並列で、コストは小さくない。意図を明確にせず放置すると、構造的に CI を整理しづらい。
- 即時の機能不良ではないので High ではない。

## 現状

`.github/workflows/build.yml:172-228` (`build_ubuntu_arm`):

- matrix: `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` x Python 3.12 / 3.13 / 3.14 = 6 ジョブ。
- runs-on: `ubuntu-24.04-arm` / `ubuntu-22.04-arm` (native arm GitHub Actions ランナー)。
- 主なステップ: `apt-get install multistrap` (実は native でも multistrap を入れている), clang-19 セットアップ, `uv sync`, `uv run python run.py build ...`, `uv build`。
- 最後に `actions/upload-artifact` の呼び出しが **無い**。
- `needs:` で参照されるのは `slack_notify` のみ (失敗通知用)。

`build_ubuntu` (x86_64 ランナーからクロスビルド) は同じターゲットで wheel を生成し `upload-artifact` する。
`publish_wheel` / `create-release` はこちらを参照する。

## 設計方針

以下 (a) (b) のどちらかを選ぶ。実装時に判断する。

(a) 検証専用ジョブとして明示する。

- ジョブ名を `build_ubuntu_arm` から `verify_ubuntu_arm` (または `native_build_check_ubuntu_arm`) にリネーム。
- ジョブのコメントに「native arm ランナーでビルドが通ることを検証するためだけのジョブ。生成 wheel は破棄。配布 wheel は `build_ubuntu` から作られるクロスビルド成果物」と明記する。
- `slack_notify.needs` の参照名も更新する。
- 削減検討: CI コスト圧縮のため Python 3.12 / 3.13 / 3.14 全てではなく代表 1 バージョンに減らすかも検討する (本 issue のスコープ外で良いが提案として記録)。

(b) native arm wheel 配布に切り替える。

- `build_ubuntu_arm` に `actions/upload-artifact` を追加し、`build_ubuntu` (x86_64 + multistrap クロス) の armv8 ビルドを廃止する。
- `publish_wheel` / `create-release` の参照を `build_ubuntu_arm` 成果物に切り替える。
- multistrap 経路 (`multistrap/ubuntu-22.04_armv8.conf` / `multistrap/ubuntu-24.04_armv8.conf`) を含む armv8 クロスビルド機構を削除できる可能性がある。issue 0061 (multistrap conf) や PR #302 (sysroot.py 移行) と整合させる。

可能であれば (b) のほうが「クロスビルドとネイティブビルドの両方を維持する複雑性」を減らせる。
ただし native arm ランナーの実行時間・キャパシティが PyPI リリースゲートに耐えられるか確認が必要。
本 issue ではまず (a) で意図明示を行い、(b) は別 issue で本格検討する流れも想定する (issue 0006 の CI 整理と連動)。

## 完了条件

- `.github/workflows/build.yml` 上で `build_ubuntu_arm` の役割が「artifact を出さない検証ジョブ」または「native arm wheel 配布元」のいずれかに明確に位置付けられている。
- (a) を選ぶ場合: ジョブ名がその役割を反映している。コメントで意図が読み取れる。`slack_notify.needs` も更新済み。
- (b) を選ぶ場合: `publish_wheel` / `create-release` が `build_ubuntu_arm` 成果物を参照する。armv8 クロスビルドが削除 (または役割縮小) されている。
- 既存の CI green が崩れないこと。
