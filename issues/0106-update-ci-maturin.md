# CI を maturin 化し wheel とクロスコンパイルを実証する

- Created: 2026-09-16
- Completed: -
- Branch: feature/update-ci-maturin
- Polished: {YYYY-MM-DD}

## 目的

maturin ベースの wheel ビルドを CI に組み込み、現行 8 プラットフォーム × Python 3.12 / 3.13 / 3.14 の wheel を作れるようにする。あわせて armv8 系のクロスコンパイルが成立するかを実証する。

## 現状

- `.github/workflows/build.yml` は 8 プラットフォーム × Python 3.12 / 3.13 / 3.14 の 24 wheel を作る。プラットフォームは ubuntu-26.04 と ubuntu-24.04 の x86_64 / armv8、raspberry-pi-os_armv8、macos-15 と macos-26 の arm64、windows-2025_x86_64 である。
- armv8 系は x86_64 runner からのクロスコンパイルで、`sysroot_builder.py` が rootfs を生成する。
- `setup.py` が manylinux tag を手動で設定し、Raspberry Pi 向けのみ `libcamerac.so` を同梱する。
- PyPI への公開対象は ubuntu-24.04 の x86_64 / armv8、macos-15 / 26 の arm64、windows-2025_x86_64、raspberry-pi-os_armv8 の 6 プラットフォームである。
- E2E テストは Python 3.13 のみを対象にしており、3.12 と 3.14 はコメントアウトされている。
- 試作ブランチでは `.github/workflows/build.yml` / `build-debug.yml` と `dev.py` が削除されたままで、CI は未再構築である。
- `shiguredo_webrtc` の `build.rs` は prebuilt libwebrtc を `shiguredo/webrtc-rs` の Release から SHA-256 検証付きで取得する。`CARGO_CFG_TARGET_OS` / `CARGO_CFG_TARGET_ARCH` と `/etc/os-release` から対象を決め、`WEBRTC_C_TARGET` で明示指定できる。
- sora-rust-sdk の対応プラットフォームは linux x86_64 / aarch64 (ubuntu-22.04 / 24.04 / 26.04、raspberry-pi-os)、macos aarch64、windows x86_64 である。sora-rust-sdk 自身の CI は native arm runner のみで、armv8 wheel のクロスコンパイル実績が無い。

## 設計方針

- `docs/migration-to-sora-rust-sdk.md` の決定事項 15 と 16 に従う。現行 8 プラットフォームを維持し、成立しないものは実証結果に基づいて落とす。落とす場合はユーザーに確認する。
- wheel のビルドは maturin を使う。`pyproject.toml` の maturin 設定で manylinux tag と同梱物を表現する。表現できない項目は `maturin` の設定ファイル (`pyproject.toml` の `[tool.maturin]`) で扱う。
- armv8 系は `WEBRTC_C_TARGET` と sysroot / リンカ設定で成立するかを実証する。実証できない場合は、native arm runner へ切り替える案と対象から落とす案をユーザーに提示する。
- Raspberry Pi OS 向けの `libcamerac.so` 同梱は libcamera の issue と連携する。
- E2E テストは Python 3.12 / 3.13 / 3.14 の全版を対象にする。
- CI では `j178/prek-action` を使い、ローカルと同じ `prek.toml` のフックを実行する (`shiguredo-python` 規約)。

## 完了条件

- maturin ベースで 8 プラットフォーム × Python 3.12 / 3.13 / 3.14 の wheel をビルドする CI が通ること。
- armv8 系のクロスコンパイルの成否が実証され、成否と根拠が issue に記録されていること。
- wheel の tag と同梱物が現行と同等であること (PyPI 公開対象 6 プラットフォーム)。
- E2E テストが Python 3.12 / 3.13 / 3.14 で動くこと。
- CI のログに機密情報の実値が残らないこと。

## 依存

- 先行: ビルド基盤を maturin へ置き換える issue から libcamera の issue までのすべて。
- 上流: 無し。
- 後続: ドキュメント追従の issue が本 issue に依存する。

## 解決方法
