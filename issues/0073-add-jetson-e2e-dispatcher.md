# NVIDIA Jetson E2E 用の trusted dispatcher を追加する

- Priority: High
- Created: 2026-07-17
- Updated: 2026-07-17
- Completed: -
- Model: GPT-5
- Branch: feature/add-jetson-e2e-dispatcher
- Polished: 2026-07-17

## 目的

default branch 上の変更不能な workflow だけが self-hosted Jetson runner を起動できる trusted dispatcher を先行追加し、0045 の feature branch code を明示承認した exact commit SHA で安全に build / E2E できる境界を作る。

本 issue は dispatcher、runner access、environment approval、source provenance、cleanup の基盤だけを扱う。Jetson wheel build は 0043、runtime E2E script / RPATH 判断は 0045、release は 0072 が扱う。

## 優先度根拠

- PR 自身が変更できる workflow を self-hosted runner の gate にすると、environment や label 条件を削除して runner を直接実行できる。
- `workflow_dispatch` は workflow file が default branch に存在する必要があるため、0045 と同じ PR で初回 bootstrap できない。
- 0045 / 0072 の実機検証と配布の信頼境界になるため High とする。

## 前提

- 0043 完了後、0045 より前に実装する。
- Jetson runner は T234 / JetPack 6 専用とし、repository / cloud secret、資格情報、不要な device を持たせない。
- 本 issue の PR 自体では feature branch code を self-hosted runner で実行せず、workflow 構造と GitHub 設定だけを確認して merge する。実機 acceptance は 0045 で行う。

## 設計方針

### workflow

`.github/workflows/dispatch-jetson-e2e.yml` を `workflow_dispatch` 専用で追加する。入力は 40 桁 lowercase commit SHA と `jetson/versions.json` の mapping key だけとし、branch / tag / arbitrary ref、runner label、environment 名、command は受け取らない。

dispatch は `develop` ref に固定して行う。preparation の最初に `github.run_attempt == 1`、`github.ref == 'refs/heads/develop'`、`github.workflow_ref` から得た workflow path / ref、`github.workflow_sha == github.sha` を検証する。API で同 commit が protected `develop` から到達可能であることを確認し、同 commit / 固定 path の workflow file と detached checkout した file を byte-for-byte で一致させる。workflow file SHA-256 は provenance として記録するが、存在しない run metadata digest との比較は要求しない。queue 待ち中に進み得る current `develop` head との完全一致は要求しない。別 branch / tag の workflow definition で開始された run と再実行 attempt は self-hosted runner へ到達させない。failure / cancellation 後は rerun せず、新しい dispatch run ID で build / approval / E2E を最初から実行する。

workflow level は `permissions: {}` とし、各 job で必要な read scope を完全列挙する。job-level `permissions` は workflow-level 権限への追加ではなく、未指定 scope が `none` になる前提で設計する。固定 environment `jetson-e2e`、固定 `concurrency: jetson-e2e` を使用する。preparation checkout は `persist-credentials: false` とし、source code を実行しない。preparation job が次を検証してから environment approval へ進む。

job ごとの権限 map は次に固定し、これ以外の scope と全ての write scope を付与しない。

- `preparation`: `actions: read` / `contents: read` / `pull-requests: read`。
- `build_pyi`: `actions: read` / `contents: read`。
- `build_jetson`: `actions: read` / `contents: read`。
- `approval-gate`: `actions: read` / `contents: read` / `pull-requests: read`。
- self-hosted E2E: `actions: read` / `contents: read`。`pull-requests: read` は付与しない。
- `attest`: `actions: read` / `contents: read`。

- SHA が本 repository の commit で、削除済み / fork object ではない。
- SHA が open PR の current head、または protected `develop` の到達可能 commit である。associated PR は state `open`、`head.sha` 完全一致、`head.repo.full_name` が本 repository であることを認証付き GitHub API で検証する。
- mapping key が source の `jetson/versions.json` の 1 entry、および `github.workflow_sha` の blob から読んだ trusted `jetson/trusted-runners.json` の 1 entry と完全一致する。current `develop` の file は参照しない。exact version の値も両 file で一致する。
- source に 0043 の `scripts/build_pyi_ci.py` / `scripts/build_jetson_ci.py` と 0045 の `scripts/e2e_jetson_ci.py` が通常 file として存在する。source code を `--help` も含めて preparation では実行せず、dispatcher 所有 parser で source の固定 schema declaration data だけを静的検証する。

3 script は top-level に `JETSON_CI_CONTRACT = {...}` という literal assignment を厳密に 1 件持つ。dispatcher parser は Python `ast` と `ast.literal_eval` だけで読み、schema version、script kind、CLI argument の名前 / 型 / required、output schema version を検証する。import、attribute access、call、式評価は行わない。missing / duplicate assignment、非 literal、unknown key、旧 / 未知 schema version、script kind 不一致を拒否する。

GitHub-hosted `build_pyi` job と `build_jetson` job を分離し、両方が同じ source SHA を detached checkout する。source build job は checkout 後に git credential を残さず、source script へ token / credential を environment variable として渡さない。

`build_pyi` は `scripts/build_pyi_ci.py` で Python 3.12 / 3.13 / 3.14 の型情報 artifact を生成する。`build_jetson` は `needs: [preparation, build_pyi]` とし、3 artifact の完全名、manifest SHA-256、source SHA を検証してから `scripts/build_jetson_ci.py` を呼ぶ。1 job 内で同一 sysroot を再利用して 3 ABI wheel を順次生成し、wheel 内型情報と 3 build manifest の sysroot / package digest 一致を確認してから upload する。

self-hosted job は artifact の全 digest / source SHA を実行前に検証してから `scripts/e2e_jetson_ci.py` を呼ぶ。source 側 workflow は reusable / composite を含めて呼び出さず、runner labels、permissions、environment、cleanup は dispatcher 内の固定値だけを使う。

dispatcher workflow definition SHA と source commit SHA は別 field に保存する。source checkout、build manifest の `source_commit_sha`、wheel source だけを source input と一致させる。

source の `scripts/e2e_jetson_ci.py` は import / `readelf` / `LD_DEBUG` / package provenance の runtime evidence payload と log だけを生成し、dispatcher run / workflow / job、trusted mapping、runner lifecycle を自己申告しない。

self-hosted job は source code を実行する前に、approval-gate output、runner context、package preflight を含む dispatcher-owned record を固有名の immutable artifact として upload する。source 実行後は runtime payload / log だけを別の固有名 artifact として upload して終了し、trusted attestation を同じ job で生成しない。source が予約済み artifact 名を先取りした場合は後続の固定 upload が conflict して job を失敗させる。

fresh GitHub-hosted `attest` job が両 artifact を run ID / 完全名で再取得し、全 producer job の `run_attempt == 1`、件数、basename、path traversal、digest を検査する。dispatcher definition SHA の trusted generator、GitHub context / API の run / workflow / job metadata、approval-gate output、trusted mapping digest、build artifact digest を結合して `jetson-e2e-attestation.json` を生成し、source payload / log と合わせた最終 `jetson-e2e-results` artifact を upload する。同一 OS user で source code を実行した self-hosted workspace、`GITHUB_ENV`、`GITHUB_PATH`、process、generator は再利用しない。

### trusted runner mapping と GitHub 保護設定

0073 は default branch に schema version 付き `jetson/trusted-runners.json` を追加する。各 entry は mapping key、JetPack marketing version、epoch を含む `nvidia-jetpack` / `nvidia-l4t-core` exact Debian version、Jetson Linux release、SoC、suite、固定 runner label を必須 field とし、0045 source PR から変更できない trusted input とする。実行時は必ず dispatcher definition と同じ `github.workflow_sha` の blob を取得し、file SHA-256 と selected entry digest を記録する。source の `jetson/versions.json` と同名 field を完全一致で比較する。unknown / missing key、型違い、部分一致、duplicate mapping key / runner label を拒否する。

selected entry digest は mapping key を entry object の必須 field として含め、float を禁止し、全 string を Unicode NFC に正規化した後、UTF-8、key sort、compact separator、ASCII escape 無しの canonical JSON に直列化した byte 列の SHA-256 とする。preparation、approval-gate、fresh GitHub-hosted `attest` job、0072 が同じ dispatcher 所有実装を使う。key 順序 / 空白だけが異なる同値 fixture は同じ digest、値が 1 つ異なる fixture は異なる digest になる既知値 test を追加する。

runner label は `^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$` に限定し、GitHub 標準 label、固定共通 label、duplicate label を拒否する。新 version / label を追加する場合は 0045 より前の独立した dispatcher 更新 PR で merge し、runner group 設定を二者確認する。

- environment `jetson-e2e`: required reviewer、self-review 禁止、deployment branch は `develop` のみ。
- runner group 名は `sora-python-sdk-jetson-e2e` に固定し、本 repository、かつ `.github/workflows/dispatch-jetson-e2e.yml@develop` だけを selected workflow として許可する。
- self-hosted `runs-on` は `group: sora-python-sdk-jetson-e2e` と labels `self-hosted` / `Linux` / `ARM64` / `Jetson` / `JetPack-6` / trusted mapping の exact label を併用する。group 名は input / source mapping から受け取らない。
- runner は `--ephemeral` の single-use だけを許可する。persistent runner fallback は設けない。workflow 外の supervisor が 1 job ごとに登録し、job 終了 / 異常終了後に unregister / re-image と health marker 確認を完了するまで次 runner を登録しない。

設定画面の environment / runner group / selected workflow / runner label を maintainer 2 名で確認し、PR に確認結果を残す。設定変更は repository 外の管理操作であり、workflow から行わない。

### runner contract と cleanup

GitHub-hosted preparation job は trusted mapping の label を job output にし、approval-gate が同じ label / mapping digest を再検証して自身の output として伝搬する。self-hosted `runs-on.labels` は直接 dependency である `needs.approval-gate.outputs.trusted_runner_label` だけを動的 label に使い、`needs.preparation` や source input を参照しない。group / label membership は GitHub server の `runs-on` selector と maintainer 2 名の外部設定確認を強制境界とし、job context に存在しない runner ID / group / 全 labels を runtime 検証しない。preflight は `runner.os` / `runner.arch` / `runner.environment` と実機 package exact version を検証する。source の `jetson/versions.json` から runner routing を決定しない。

runner は 0045 が定義する canonical CPython path と exact JetPack / Jetson Linux label を持つ。self-hosted job の開始時に前回 process / workspace / virtual environment が無いことを検証する。

`if: always()` の固定最終 step で child process、temporary directory、virtual environment、download artifact、追加 environment variable を除去する。これは補助 cleanup とし、隔離保証は ephemeral runner supervisor の unregister / re-image / health marker で行う。

post-job の unregister / re-image / health marker は job 終了後に確定するため、job 内で upload する attestation へ含めない。attestation は runner lifecycle request `ephemeral` と実行開始時の preflight health result を保持する。post-job supervisor result は次 runner を登録する前の repository 外運用記録とし、release provenance の成功条件へ偽装して混ぜない。

### approval と再検証

preparation job summary に source SHA、open PR URL / current head、mapping entry、trusted runner label、dispatcher definition SHA を表示する。environment reviewer は current PR head と input SHA の一致を確認してから承認する。

job graph を次に固定する。

- `preparation`
- `build_pyi`: `needs: preparation`
- `build_jetson`: `needs: [preparation, build_pyi]`
- `approval-gate`: `needs: [preparation, build_jetson]`、固定 `environment: jetson-e2e`、job-level `actions: read` / `contents: read` / `pull-requests: read`
- self-hosted E2E: `needs: [approval-gate, build_jetson]`。environment / `pull-requests: read` は付与しない
- `attest`: fresh GitHub-hosted runner、`needs: [approval-gate, build_jetson, self-hosted E2E]`。job-level `actions: read` / `contents: read`

environment approval 後に `approval-gate` が open PR current head または `develop` reachability を認証付き API で再検証する。さらに current protected `develop` から dispatcher workflow file と trusted mapping の同じ selected entry を取得し、workflow file SHA-256 と canonical selected entry digest が実行開始時に pin した値と一致することを要求する。current head 自体の一致や trusted mapping file 全体の一致は要求しないため、dispatcher と selected entry を変えない unrelated commit / 別 entry 追加は許可する。dispatcher または selected entry が更新・撤回された stale run は self-hosted runner へ到達させない。

成功 output に source SHA、mapping key、trusted runner label、build artifact digest 集合、trusted mapping file SHA-256 / selected entry digest を持たせ、self-hosted job が再検証する。PR head が変わった場合、または trusted definition が変わった場合は古い run を失敗させ、新 SHA / run ID で再 dispatch / 再承認する。

## 完了条件

- dispatcher が default branch に存在し、任意 command / ref / runner / environment input を受け取らない。
- `run_attempt == 1` だけを許可し、rerun artifact を初回 attempt と混在させない。失敗時は新しい run を dispatch する。
- approval-gate が current protected `develop` の dispatcher file / selected trusted entry digest を pin 済み値と再照合し、撤回済み定義の stale run を拒否する。
- dispatch ref / workflow definition が protected `develop` と一致する。
- workflow level が `permissions: {}` で、全 job の job-level permission map が設計値と完全一致し、write scope が無い。
- GitHub-hosted preparation / approval-gate が `actions: read` / `contents: read` / `pull-requests: read` を使い、source SHA / open PR ownership / current head / trusted mapping / runner label / static schema を self-hosted 実行前に検証する。
- 固定 group `sora-python-sdk-jetson-e2e` が default branch の dispatcher workflow だけを許可し、PR 内の別 workflow や同 label の別 group runner を使用できない。
- environment approval、無 secret / read-only permission、single concurrency、実行前 provenance、ephemeral supervisor、`if: always()` cleanup が固定 workflow にある。
- fresh GitHub-hosted `attest` job が source 生成 runtime evidence payload と trusted `jetson-e2e-attestation.json` を分離し、attestation に workflow definition SHA、source SHA、`github.workflow_sha` に pin した trusted mapping file SHA-256 / selected entry digest、runner lifecycle request `ephemeral`、preflight health result、build / E2E payload digest を別 field で残す。
- post-job supervisor result を job 内 artifact に含めず、次 runner 登録前に repository 外で unregister / re-image / health marker を確認する。
- 本 issue の PR では未 merge feature code を runner 上で実行しない。

## 解決方法

1. input validation と read-only GitHub-hosted preparation job を追加する。
2. 固定 build / self-hosted E2E / fresh GitHub-hosted attest / cleanup job の skeleton を追加する。
3. environment / runner group / selected workflow / runner lifecycle を管理者が設定・二者確認する。
4. invalid SHA / fork / arbitrary ref / unknown mapping / source workflow invocation の拒否を GitHub-hosted job で検証する。
5. 0045 で初回の approved source SHA を実機実行する。

`actionlint` で workflow 構文、`needs`、fixed environment、group selector、input 集合を検査する。workflow 構造 test は YAML を parse し、workflow-level `permissions: {}` と全 job の job-level permission map、self-hosted `runs-on` の label output 参照を固定値で比較する。preparation / mapping / SHA / contract declaration / attestation validation は dispatcher 所有の pure script に分離し、invalid SHA 形式、unknown mapping、fork / closed PR、head mismatch、invalid / duplicate runner label、workflow SHA と trusted mapping blob の不一致、payload digest 改変、非 literal contract を local fixture で検証する。source workflow / composite action を呼ばないことも workflow 構造 test で確認する。

## 変更履歴

release artifact や SDK runtime を変更せず、CI security boundary だけを追加するため `CHANGES.md` には記載しない。

## ロールバック

0045 / 0072 が未実装なら runner group を offline にして dispatcher workflow を revert する。0045 / 0072 が実装済みなら新規 Jetson release を停止し、0072、0045、0073 の逆順で revert または無効化する。self-hosted runner group の selected workflow access も同時に削除する。

## 参考資料

- [GitHub Actions: `workflow_dispatch`](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatch)
- [GitHub Actions: self-hosted runner access](https://docs.github.com/en/enterprise-cloud@latest/actions/how-tos/manage-runners/self-hosted-runners/manage-access)
- [GitHub Actions: secure use](https://docs.github.com/en/actions/reference/security/secure-use)
