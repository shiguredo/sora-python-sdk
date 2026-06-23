# `gil_scoped_acquire` / `gil_scoped_release` のメンバ未初期化による UB を修正する

- Priority: Medium
- Created: 2026-06-23
- Model: Opus 4.7
- Branch: feature/fix-gil-scope-uninitialized-member

## 目的

`src/gil.h` の `gil_scoped_acquire` / `gil_scoped_release` は `Py_IsInitialized() == false` のときに早期 return する分岐を持っているが、メンバ変数がデフォルト初期化されていないため、その分岐に入るとデストラクタで未初期化メンバを参照する可能性がある。これは規格上の未定義動作 (UB) であり、最適化や ABI 変化を契機にいつ問題化してもおかしくない。

発生条件は Python シャットダウン中の限定的なケースに見えるが、未初期化メンバは「アドレスの bit パターンが運良くゼロだったら助かる」という運頼みになっており、根本的に直すべき欠陥である。

## 優先度根拠

Medium とする。

- 現在ユーザー報告にあるクラッシュとは直結していないため High ではない。
- ただしクラスのコメント自体が「Python シャットダウン中に呼ばれた場合の挙動を考慮するため自前で用意した」と書いているとおり、まさにそのシャットダウン経路で UB を踏む構造になっている。`Py_Finalize` 後に発火する破棄系コードパスは再現が難しい一方、起きると「終了時にだけたまにクラッシュする」という最悪のデバッグ条件を生む。
- 修正コストは極めて小さい (デフォルト初期化を 2〜3 行入れるだけ) ため、対費用効果が非常に高い。Low に落とすほどの軽い欠陥ではない。

## 現状

### `gil_scoped_acquire`

`src/gil.h:13-34`:

```cpp
struct gil_scoped_acquire {
 public:
  gil_scoped_acquire(const gil_scoped_acquire&) = delete;
  gil_scoped_acquire(gil_scoped_acquire&&) = delete;

  gil_scoped_acquire() noexcept {
    if (!Py_IsInitialized()) {
      return;          // initialized も state も未初期化のまま return する
    }
    state = PyGILState_Ensure();
    initialized = true;
  }
  ~gil_scoped_acquire() {
    if (!initialized || !Py_IsInitialized()) {
      return;
    }
    PyGILState_Release(state);
  }

 private:
  bool initialized;          // 未初期化
  PyGILState_STATE state;    // 未初期化
};
```

`Py_IsInitialized() == false` で早期 return すると、`initialized` / `state` ともに値が確定しない。デストラクタで `initialized` を読む時点で UB。`initialized` がたまたま非ゼロだった場合、未初期化の `state` を持って `PyGILState_Release` に渡すとさらに悪化する。

### `gil_scoped_release`

`src/gil.h:38-58`:

```cpp
struct gil_scoped_release {
 public:
  gil_scoped_release() noexcept {
    if (!Py_IsInitialized()) {
      return;          // state が未初期化のまま return する
    }
    state = PyEval_SaveThread();
  }
  ~gil_scoped_release() {
    if (state == nullptr || !Py_IsInitialized()) {
      return;
    }
    PyEval_RestoreThread(state);
  }

 private:
  PyThreadState* state;     // 未初期化
};
```

こちらはデストラクタで `state == nullptr` を読むため、未初期化ポインタの値次第で `PyEval_RestoreThread(state)` を呼んでしまう。`PyThreadState*` の値が不定のままシステムコールに渡る、典型的な UB 経路。

### 発火条件

- 通常運用中は `Py_IsInitialized() == true` のため、コンストラクタの末尾で確実に初期化される。問題は出ない。
- Python の `Py_Finalize` 後に破棄処理が走るシナリオ (`nanobind` の static 破棄、`SoraConnection` のスレッド終端での後始末など) で発火しうる。

## 設計方針

メンバをデフォルト初期化する。

```cpp
struct gil_scoped_acquire {
  // ...
 private:
  bool initialized = false;
  PyGILState_STATE state{};
};

struct gil_scoped_release {
  // ...
 private:
  PyThreadState* state = nullptr;
};
```

これだけで未初期化メンバの参照は消える。`gil_scoped_release` のデストラクタが既に `state == nullptr` チェックを持っているので、`nullptr` 初期化との整合性も取れる。

合わせて、`GILLock` の `state_` (`src/gil.h:78`) はすでに `nullptr` で初期化されているが、念のため同じ規約を `gil_scoped_acquire` / `gil_scoped_release` 側にも揃え、すべての GIL 関連メンバが「コンストラクタ本体に到達する前に有意な値を持っている」状態にする。

UB 修正に伴うテストの追加方針:

- `Py_Finalize` 後の破棄を再現するユニットテストは現実的には書きづらいため、修正の根拠と修正方針をコメントとして残す (「early return 時のメンバ値が観測される可能性があるため明示的にデフォルト初期化する」)。
- 既存テストが pass することは確認する。

## 完了条件

- `gil_scoped_acquire::initialized` / `gil_scoped_acquire::state` / `gil_scoped_release::state` がメンバ初期化子で確実な初期値を持つこと。
- 早期 return パスを経由したデストラクタの実行で未初期化メンバを読まないこと。
- 修正の意図 (Python シャットダウン中の早期 return 経路で UB を踏まないため) がコメントで明示されていること。
- 既存テストが pass すること。
