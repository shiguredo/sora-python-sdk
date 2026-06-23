# Jetson ビルドが Python 3.10 ハードコードで `requires-python >= 3.12` と矛盾している問題を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-jetson-python-version-mismatch

## 目的

`run.py:332-351` の Jetson 分岐は `Python_ROOT_DIR` と `NB_SUFFIX` を `python3.10` / `cpython-310` 固定で指定しているが、`pyproject.toml:5` で `requires-python = ">= 3.12"` を宣言している。これは矛盾しており、Jetson 向けに wheel をビルドしてもインストール時に Python バージョン制約で弾かれるか、ビルド済み拡張が壊れている。

矛盾を解消し、Jetson の対応方針を明確にする。

## 優先度根拠

Medium とする。

- Jetson プラットフォーム向けのリリース wheel が事実上「ビルドできても使えない」状態である構造バグ。
- High ではない理由は、Jetson は限定的なプラットフォームで、影響範囲が他 OS より小さい。issue 0004 (Jetson / RPi の刷新) と関連する大きな構造判断を伴うため即時修正は難しい。
- Low ではない理由は、リリースアーティファクトに対応プラットフォームとして Jetson が含まれている以上、矛盾状態の放置は信頼性を損なう。

## 現状

`pyproject.toml:5`:

```toml
requires-python = ">= 3.12"
```

`pyproject.toml:15-17`:

```toml
"Programming Language :: Python :: 3.12",
"Programming Language :: Python :: 3.13",
"Programming Language :: Python :: 3.14",
```

一方、`run.py:332-351` の Jetson 分岐:

```python
elif platform.target.os == "jetson":
    sysroot = os.path.join(install_dir, "rootfs")
    cmake_args += [
        ...
        f"-DPython_ROOT_DIR={cmake_path(os.path.join(sysroot, 'usr', 'include', 'python3.10'))}",
        "-DNB_SUFFIX=.cpython-310-aarch64-linux-gnu.so",
    ]
```

Jetson のベース OS (Ubuntu 20.04 / 22.04 ベースの L4T) のシステム Python が 3.10 系であることに起因する。Ubuntu 24.04 ベースの新しい JetPack に追従していれば 3.12 が使えるが、現状の rootfs は古い。

他のクロスコンパイル分岐 (raspberry-pi-os など) は `get_python_version()` で動的に取っているため、ホスト側 Python に合わせて wheel が作られる。Jetson だけがハードコードという非対称な状態。

## 設計方針

3 つの選択肢があり、本 issue では決定せず方針を並べ、選定は実装時に行う:

1. **Jetson rootfs を新 JetPack (Ubuntu 24.04 ベース) に移行して Python 3.12 系にする** (issue 0004 と統合)
   - 本筋。`get_python_version()` ベースの動的解決にできる。
   - JetPack 6 系の rootfs 入手と動作確認が必要。
2. **Jetson 向けに `requires-python` を引き下げる**
   - 別パッケージ (例: `sora_sdk_jetson`) に分割し、そちらだけ `requires-python = ">= 3.10"` にする。
   - 既存パッケージとの 2 重メンテになる。
3. **Jetson サポートを当面 pending にし、wheel を出さない**
   - 矛盾は無くなるがユーザ影響あり。要判断。

短期的には 3 が最も安全で、中期的に 1 へ移行するのが妥当。

raspberry-pi-os 分岐 (`run.py:352-372`) は `get_python_version()` で動的取得しているので、Jetson もこの方式に揃えることが第一歩。ただし sysroot 側に対応する Python ヘッダが入っている必要がある。

## 完了条件

以下のいずれかを満たすこと:

- Jetson の `Python_ROOT_DIR` / `NB_SUFFIX` が `get_python_version()` 由来の動的値になり、rootfs も Python 3.12 以上を提供していること。
- Jetson 向けが別パッケージとして分離され、それ単独の `requires-python` が rootfs の Python と整合していること。
- Jetson サポートを一時的に外す判断をした場合は、`pyproject.toml` の classifier・CI・README から Jetson を取り除き、issue が `pending/` に移動されていること。

いずれにせよ `run.py:332-351` のハードコードが `pyproject.toml` の `requires-python` と整合していること、CI で Jetson 向け wheel が生成された場合に動作確認できる手段が用意されていること。
