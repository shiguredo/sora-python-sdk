# cmake 関数 _sora_fetch_rootfs の dry-run 検証を追加する

- Priority: Medium
- Created: 2026-06-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/add-sora-fetch-rootfs-dry-run
- Polished: {YYYY-MM-DD}

## 目的

0024 で `cmake/scripts/fetch_deps.cmake` に追加した `_sora_fetch_rootfs(rootfs_dir json_config)` 関数は、 「scikit-build-core 経路では呼び出さない、 cross-compile 経路が追加されたときに呼び出しを足す」 という設計で merge された。 そのため cmake は関数定義の構文 (`function...endfunction`、 引数記述) は parse するが、 **関数本体のロジック (`execute_process` の引数渡し、 `RESULT_VARIABLE` の比較、 `${CMAKE_SOURCE_DIR}/sysroot.py` の resolution など) は呼ばれるまで評価されない**。 後続 cross 系 issue が実呼び出しに切り替えた瞬間に bug が顕在化するリスクがある。

このリスクを下げるため、 後続 cross 系 issue が実装着手する前に **「実呼び出ししてみる」 dry-run 検証手順** を整える。

## 優先度根拠

Medium:

- 0024 単体では `_sora_fetch_rootfs` は呼ばれないため、 即座のサービス影響はない
- 後続 cross 系 issue (ubuntu armv8 / jetson / raspberry-pi-os 復活) が並行で複数走る前に dry-run 手順を整備しておかないと、 各 issue で同じ問題を個別に踏むことになる
- 0025 (sysroot.py 単体テスト追加) と並行できる独立した issue

## 現状

- `cmake/scripts/fetch_deps.cmake` (380-403 行) に `_sora_fetch_rootfs(rootfs_dir json_config)` 関数定義あり
- 関数本体は `execute_process(COMMAND "${Python_EXECUTABLE}" "${_script}" build --config ... --dest ...)` と `RESULT_VARIABLE _rootfs_result` で `if(NOT _rootfs_result EQUAL 0) message(FATAL_ERROR ...) endif()`
- 関数の呼び出しは メインスクリプト中 0 件 (0024 完了条件で確認済み)
- 検証手段は手元の `cmake -P` で「関数定義部分の文法エラーが出ないこと」 を確認するだけ (0024 issue ファイル内に明示)
- `_sora_fetch_rootfs` の動的検証は `sysroot.py build` が動く環境 (ubuntu-24.04 x86_64 host + dpkg-deb >= 1.21) でしか実行できない

## 設計方針

### dry-run スクリプトの追加

- `cmake/scripts/` 配下に `test_fetch_rootfs.cmake` 等の検証スクリプトを置く (本体スクリプトと同じ場所だが `test_` prefix で区別)
- スクリプト内容: `${Python_EXECUTABLE}` / `${CMAKE_SOURCE_DIR}` を引数 / 環境変数から受け取り、 `include(${CMAKE_SOURCE_DIR}/cmake/scripts/fetch_deps.cmake)` の代わりに `_sora_fetch_rootfs` 関数定義部分だけを `file(READ)` + `string(REGEX MATCH)` で抜き出して評価するか、 もしくは `fetch_deps.cmake` を `OPTIONAL` モードで include した後 `_sora_fetch_rootfs(...)` を直接呼ぶ
- メインスクリプト全体を実行すると `deps.json` 読み込み・WebRTC / Sora / Boost / OpenH264 / LLVM 取得まで走るため、 dry-run 用には関数定義だけ抽出する経路が必要
- 代替案: `_sora_fetch_rootfs` 関数定義を `cmake/scripts/sora_fetch_rootfs.cmake` 等の単独ファイルに切り出し、 `fetch_deps.cmake` から `include` する。 そうすれば dry-run スクリプトも単独 include できる

### CI への組み込み

- `.github/workflows/build.yml` の `build_ubuntu` job に dry-run step を追加するか、 別 workflow (`.github/workflows/sysroot-dry-run.yml`) を新設するかを設計時に判断する
- 推奨: `build_ubuntu` 内に `_sora_fetch_rootfs` dry-run step を 1 つ追加。 4 platform の JSON に対して順次実行 (jetson は時間がかかるため `--jobs 4` + cache 利用)
- dry-run は実際に rootfs を構築するため `dpkg-deb` 必須。 `runs-on: ubuntu-24.04` で実行
- キャッシュ: `actions/cache` で `<dest>/.debs/` を repo / commit 単位でキャッシュし、 dry-run 時間を短縮 (初回 30 分 → 2 回目以降 5 分以下を目標)

### dry-run の終了条件

- 4 platform 全てで `_sora_fetch_rootfs` が exit code 0 で完了
- 構築された `<rootfs>/.sysroot.stamp` が存在
- 構築された `<rootfs>/usr/include/aarch64-linux-gnu/sys/types.h` が存在 (libc6-dev 展開確認)
- 上記が CI green として記録される

## 完了条件

- `_sora_fetch_rootfs` の dry-run 検証手段が手元・CI 双方で実行可能になる
- CI で dry-run が green であることを `.github/workflows/build.yml` (もしくは新設 workflow) で確認できる
- 4 platform (ubuntu-22.04_armv8 / ubuntu-24.04_armv8 / ubuntu-22.04_armv8_jetson / raspberry-pi-os_armv8) すべてで dry-run pass
- dry-run の結果ログが PR description (本 issue の PR) に貼られる
- dry-run の実行手順が `cmake/scripts/README.md` 等で参照可能 (新規 README 追加か `cmake/scripts/fetch_deps.cmake` の関数 docstring に手順を追記するかは設計時に決定)

## 解決方法

1. `_sora_fetch_rootfs` 関数定義を `cmake/scripts/sora_fetch_rootfs.cmake` に切り出し、 `fetch_deps.cmake` から include (推奨アプローチの場合)
2. `cmake/scripts/test_fetch_rootfs.cmake` を新設 (引数 / 環境変数から Python / SOURCE_DIR / target 名を受け取る dry-run スクリプト)
3. `.github/workflows/build.yml` の `build_ubuntu` job に dry-run step を追加
4. `actions/cache` で `.debs/` キャッシュを設定
5. 手元での dry-run 手順を `cmake/scripts/fetch_deps.cmake` 内 `_sora_fetch_rootfs` 関数の上にコメントとして記載 (issue 参照ではなく具体的なコマンドのみ)
6. PR description に 4 platform 全ての dry-run ログを貼る

## 関連

- 0024 (closed): `_sora_fetch_rootfs` 関数定義を追加した親 issue。 関数本体の動的検証は本 issue で扱う
- 0025 (open): sysroot.py 単体テスト追加。 本 issue とは独立 (cmake 経路 vs python 経路の検証)
