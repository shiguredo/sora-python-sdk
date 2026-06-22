# multistrap 経路から sysroot.py 経路への移行

- Priority: High
- Created: 2026-06-22
- Completed: -
- Model: Opus 4.7
- Branch: feature/change-replace-multistrap-with-sysroot
- Polished: -

## 目的

cross-compile 用 sysroot の構築経路を multistrap から自前 Python スクリプト `sysroot.py` に切り替える。Ubuntu 26.04 で multistrap が廃止されること、および既存 CI で multistrap 本体に `sed` でパッチを当てる運用が脆いことに対応する。

## 優先度根拠

High:

- Ubuntu 26.04 で multistrap パッケージが提供されなくなる予定。Ubuntu 26.04 runner に切り替える前に対応が必要
- 既存 CI で `sudo sed -e '...AllowInsecureRepositories=true' -i /usr/sbin/multistrap` で multistrap 本体にパッチを当てており、multistrap が更新されるたびに壊れるリスクがある
- 後続の cross-compile 系 issue (ubuntu armv8 / jetson / RPi) は本 issue の `sysroot.py` を共通基盤として再利用する設計。本 issue を先行させないと、後続 issue で同じ仕組みを書き直す

## 現状

- `buildbase.py:install_rootfs` (L1074-1118) が `multistrap --no-auth -a arm64 -d <rootfs_dir> -f <conf>` を呼んで rootfs を作っていたが、 0016 で完了した scikit-build-core 移行に伴い `run.py` / `buildbase.py` 経路は使われなくなっており、 0022 で削除予定
- 現在 scikit-build-core 経路には cross-compile sysroot を構築する仕組みが存在しない (0017 / 0019 / 0020 が空白を埋める想定だったが、それぞれ別アプローチで方針が分かれていた)
- `multistrap/*.conf` 4 ファイル:
  - `multistrap/ubuntu-22.04_armv8.conf` (jammy / `libstdc++-11-dev` ほか)
  - `multistrap/ubuntu-24.04_armv8.conf` (noble / `libstdc++-13-dev` ほか)
  - `multistrap/ubuntu-22.04_armv8_jetson.conf` (jammy + repo.download.nvidia.com r36.3 common + t234 / `libstdc++-10-dev` + `nvidia-jetpack` + `nvidia-l4t-camera` + `nvidia-l4t-multimedia`)
  - `multistrap/raspberry-pi-os_armv8.conf` (bookworm + archive.raspberrypi.org / `libstdc++-11-dev` + `libcamera-dev` ほか)
- `.github/workflows/build.yml` の `build_ubuntu` job 内 (L139-146 / L205-214 付近) で `sudo apt-get -y install multistrap binutils-aarch64-linux-gnu` + multistrap 本体への `sed` パッチを実行
- 参考: webrtc-rs (`/Users/voluntas/shiguredo/webrtc-rs/sysroot/*.json`) が同種の sysroot 構築を Rust 製 `shiguredo_sysroot` で行っており、JSON 設定スキーマが定義されている

## 設計方針

### sysroot.py の新設

- リポジトリルートに `sysroot.py` を新規作成する
- `cmake/scripts/fetch_deps.cmake` から `execute_process(COMMAND ${Python_EXECUTABLE} ${CMAKE_SOURCE_DIR}/sysroot.py build --config sysroot/<name>.json --dest <install_dir>/rootfs)` で呼ばれる単一スクリプト
- 処理フロー:
  1. JSON 設定ファイルをパース (webrtc-rs と互換のスキーマ)
  2. 各 repo の `dists/<suite>/<component>/binary-<arch>/Packages.xz` (なければ `Packages.gz`) を取得・解析
  3. `packages` フィールドに列挙されたパッケージとその依存パッケージ (multistrap の `unpack=true` 相当の浅い依存解決) の `.deb` の URL を解決
  4. 並列ダウンロード
  5. `dpkg-deb -x <package>.deb <dest>` で展開
  6. `<dest>` 内の絶対パス symlink を相対パスに置換 (既存 `buildbase.py:install_rootfs` L1079-1100 と同等)
  7. usrmerge シンボリックリンク補完 (Ubuntu 24.04+ で必要)
  8. jetson 用 `libnvbuf_fdmap.so` 補完 (既存 `buildbase.py:install_rootfs` L1101-1117 移植)
- キャッシュ: JSON ファイルの MD5 を stamp 値とし、stamp が一致すれば再構築をスキップ (既存 `run.py:60-67` の `version_md5` と同等)
- 依存追加なし: Python 3.12 標準ライブラリのみ使用 + 外部コマンドは `dpkg-deb` のみ
- repo entry に `allow_insecure: true` (任意) を追加して GPG 鍵検証を無効化できるようにする (multistrap の `--no-auth` 相当。 NVIDIA / Raspberry Pi 公式リポジトリで必要)

### sysroot/*.json の新設

- webrtc-rs (`/Users/voluntas/shiguredo/webrtc-rs/sysroot/*.json`) と同じ JSON スキーマで書く
- Rust 固有の `rust_target` / `linker` / `cc` / `cxx` フィールドはスキーマ互換のため残す (Python では無視する)
- 対象 4 ファイル:

| ファイル | suite | 主要 packages | 追加 repo |
|---|---|---|---|
| `sysroot/ubuntu-22.04_armv8.json` | jammy | `libc6-dev`, `libstdc++-11-dev`, `libxext-dev`, `libdbus-1-dev` | - |
| `sysroot/ubuntu-24.04_armv8.json` | noble | `libc6-dev`, `libstdc++-13-dev`, `libxext-dev`, `libdbus-1-dev` | - |
| `sysroot/ubuntu-22.04_armv8_jetson.json` | jammy (`ports.ubuntu.com`) | `libc6-dev`, `libstdc++-10-dev`, `libxext-dev`, `libdbus-1-dev`, `nvidia-jetpack`, `nvidia-l4t-camera`, `nvidia-l4t-multimedia` | `repo.download.nvidia.com/jetson/common` r36.3, `repo.download.nvidia.com/jetson/t234` r36.3 (どちらも `allow_insecure: true`) |
| `sysroot/raspberry-pi-os_armv8.json` | bookworm (`deb.debian.org`) | `libc6-dev`, `libstdc++-11-dev`, `libcamera-dev`, `libasound2-dev`, `libpulse-dev`, `libudev-dev`, `libexpat1-dev`, `libnss3-dev`, `libxext-dev`, `libxtst-dev` | `archive.raspberrypi.org` bookworm (`allow_insecure: true`) |

### fetch_deps.cmake への組み込み

- `_sora_fetch_rootfs(rootfs_dir json_config stamp_path)` 関数を追加する
- 関数内で `execute_process(COMMAND ${Python_EXECUTABLE} ${CMAKE_SOURCE_DIR}/sysroot.py build --config <json_config> --dest <rootfs_dir>)` を実行する
- `SORA_PYTHON_SDK_PLATFORM` が cross 系 (`ubuntu-*_armv8` / `ubuntu-*_armv8_jetson` / `raspberry-pi-os_armv8`) のときに呼ぶ
- 出力契約: cross 時のみ `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` を `set(... CACHE PATH "" FORCE)` で設定する (native 時は触らない)
- toolchain ファイル新設や pyproject.toml override 追加など、 platform ごとの cross 個別対応は本 issue では行わない (後続の cross 系 issue で扱う)

### 削除対象

- `multistrap/` ディレクトリ (4 ファイル)
- `.github/workflows/build.yml` 内の `multistrap` パッケージインストール step (`sudo apt-get -y install multistrap` の 2 箇所)
- `.github/workflows/build.yml` 内の multistrap 本体への `sed -e '...AllowInsecureRepositories=true' -i /usr/sbin/multistrap` パッチ step (2 箇所)
- 補足: `binutils-aarch64-linux-gnu` のインストールは aarch64 用 linker / strip として引き続き必要なので残す

## 完了条件

- ubuntu-24.04 x86_64 host で次の 4 コマンドが成功する:
  - `python sysroot.py build --config sysroot/ubuntu-22.04_armv8.json --dest /tmp/rootfs-ubuntu-22.04`
  - `python sysroot.py build --config sysroot/ubuntu-24.04_armv8.json --dest /tmp/rootfs-ubuntu-24.04`
  - `python sysroot.py build --config sysroot/ubuntu-22.04_armv8_jetson.json --dest /tmp/rootfs-jetson`
  - `python sysroot.py build --config sysroot/raspberry-pi-os_armv8.json --dest /tmp/rootfs-rpi`
- 4 つの rootfs について次が確認できる:
  - `<rootfs>/usr/include/aarch64-linux-gnu/sys/types.h` が存在 (`libc6-dev` 展開)
  - `<rootfs>/usr/include/c++/*/cstddef` が存在 (`libstdc++-*-dev` 展開)
  - 絶対パスの symlink が rootfs 内に残っていない
- jetson rootfs について追加で次が確認できる:
  - `<rootfs>/usr/lib/aarch64-linux-gnu/tegra/libnvbuf_fdmap.so` または `<rootfs>/usr/lib/aarch64-linux-gnu/nvidia/libnvbuf_fdmap.so` の symlink が補完されている
- RPi rootfs について追加で次が確認できる:
  - `<rootfs>/usr/include/libcamera/libcamera.h` 相当のヘッダが存在
- 2 回目以降の実行で JSON ファイルが変わっていなければ rootfs が再構築されない (stamp ファイルが残る)
- `multistrap/` ディレクトリと `.github/workflows/build.yml` 内の multistrap 関連コマンドが完全に削除される
- 撤回した 0017 / 0019 / 0020 の代替として、本 issue の `sysroot.py` を共通基盤として参照する後続 issue を別途起票する (本 issue 自体の完了条件には含めない)

## 解決方法

### sysroot.py の追加

リポジトリルートに新規作成する。 CLI 構造:

```
python sysroot.py build --config <json> --dest <dir>
```

主要関数 (実装方針):

- `parse_config(path: Path) -> SysrootConfig`: JSON パーサ
- `fetch_packages_index(repo: Repo) -> dict[str, PackageMeta]`: `Packages.xz` の取得と解析
- `resolve_dependencies(roots: list[str], indices: dict) -> list[PackageMeta]`: 浅い依存解決
- `download_debs(packages: list[PackageMeta], cache_dir: Path) -> list[Path]`: 並列ダウンロード
- `extract_debs(debs: list[Path], dest: Path) -> None`: `dpkg-deb -x` 呼び出し
- `fix_absolute_symlinks(root: Path) -> None`: 絶対 symlink を相対 symlink に変換
- `ensure_usrmerge_symlinks(root: Path) -> None`: usrmerge シンボリックリンク補完
- `fix_jetson_libnvbuf_fdmap(root: Path) -> None`: jetson 用 symlink 補完 (config の name が jetson のときのみ呼ぶ)

### sysroot/*.json の追加

リポジトリルートに `sysroot/` ディレクトリを新規作成し、 4 ファイルを配置する。スキーマ例 (jetson):

```json
{
    "name": "ubuntu-22.04_armv8_jetson",
    "arch": "arm64",
    "rust_target": "aarch64-unknown-linux-gnu",
    "linker": "aarch64-linux-gnu-gcc",
    "cc": "aarch64-linux-gnu-gcc",
    "cxx": "aarch64-linux-gnu-g++",
    "cflags": ["-isystem", "$SYSROOT/usr/include/aarch64-linux-gnu", "-isystem", "$SYSROOT/usr/include"],
    "cxxflags": [],
    "packages": ["libc6-dev", "libstdc++-10-dev", "libxext-dev", "libdbus-1-dev",
                 "nvidia-jetpack", "nvidia-l4t-camera", "nvidia-l4t-multimedia"],
    "repos": [
        {"url": "http://ports.ubuntu.com", "suites": ["jammy", "jammy-updates", "jammy-security"], "components": ["main", "universe"]},
        {"url": "https://repo.download.nvidia.com/jetson/common", "suites": ["r36.3"], "components": ["main"], "allow_insecure": true},
        {"url": "https://repo.download.nvidia.com/jetson/t234", "suites": ["r36.3"], "components": ["main"], "allow_insecure": true}
    ]
}
```

### cmake/scripts/fetch_deps.cmake の更新

`_sora_fetch_rootfs` 関数を追加し、メインスクリプトから cross 系 platform 時に呼び出す。

### multistrap/ の削除

`multistrap/` ディレクトリと配下 4 ファイルを削除する。

### .github/workflows/build.yml の更新

- `multistrap` apt-get install step を削除 (2 箇所)
- multistrap 本体への `sed` パッチ step を削除 (2 箇所)
- `binutils-aarch64-linux-gnu` のインストールは残す

### CHANGES.md の更新

`## develop` の `[CHANGE]` グループに次を追加する (`shiguredo-changelog` 規約に従う):

```
- [CHANGE] cross-compile 用 sysroot の構築を multistrap から sysroot.py に切り替える
  - @voluntas
```

## ロールバック

`sysroot.py` の根本設計 (APT Packages Index 直接解析 + `dpkg-deb -x` 展開) に起因する不具合で追加コミットでは修正できない場合に revert を選ぶ。個別パッケージ解決の不具合や JSON 設定の誤りは追加コミットで前進させる。

手順: `git revert -m 1 <merge-commit>` で revert PR を作成、 `multistrap/` ディレクトリと CI step が復活していること、 `cmake/scripts/fetch_deps.cmake` の `_sora_fetch_rootfs` 呼び出しが消えていることを確認する。
