#ifndef GIL_H_
#define GIL_H_

// Python.h は他のヘッダより先に include する必要がある
// https://docs.python.org/3/c-api/intro.html#include-files
#include <Python.h>

#include <mutex>

// nanobind::gil_scoped_acquire は終了処理中（Py_IsInitialized() == false 時）に呼ばれた場合の
// 挙動を考えていないので、自前で用意する
struct gil_scoped_acquire {
 public:
  gil_scoped_acquire(const gil_scoped_acquire&) = delete;
  gil_scoped_acquire(gil_scoped_acquire&&) = delete;

  gil_scoped_acquire() noexcept {
    if (!Py_IsInitialized()) {
      return;
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
  bool initialized;
  PyGILState_STATE state;
};

// nanobind::gil_scoped_release は終了処理中（Py_IsInitialized() == false 時）に呼ばれた場合の
// 挙動を考えていないので、自前で用意する
struct gil_scoped_release {
 public:
  gil_scoped_release(const gil_scoped_release&) = delete;
  gil_scoped_release(gil_scoped_release&&) = delete;

  gil_scoped_release() noexcept {
    if (!Py_IsInitialized()) {
      return;
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
  PyThreadState* state;
};

// condition_variable_any で GIL を利用するためにアダプトしたクラス
struct GILLock {
  void lock() {
    // unlock 中に全ての処理が終わって Py_Finalize の終了処理中に起こされることがあるので、
    // その場合は PyEval_RestoreThread を呼び出さない。
    if (state_ == nullptr || !Py_IsInitialized()) {
      return;
    }
    PyEval_RestoreThread(state_);
    state_ = nullptr;
  }
  void unlock() {
    assert(state_ == nullptr);
    if (!Py_IsInitialized()) {
      return;
    }
    state_ = PyEval_SaveThread();
  }
  PyThreadState* state_ = nullptr;
};

// GIL と std::mutex を束ねて std::condition_variable_any に渡すための合成ロック。
//
// 「GIL を保持して入場し、待機中だけ GIL と mutex の両方を解放したい」場面で使う。
// condition_variable_any は待機のブロック中に unlock() を、起床時に lock() を呼ぶ
// ため、これにより待機中は GIL と mutex の両方が解放され、predicate 評価時には
// 両方が取得済みになる。
//
// 前提・約束:
// - 構築時に GIL を呼び出し側が保持していること。構築時に mutex を取得し、
//   「GIL と mutex の両方を保持した locked 状態」で待機に渡せるようにする。
// - lock() は GIL 取得 → mutex ロック、unlock() は mutex アンロック → GIL 解放の
//   順で行う。GIL を取得してから mutex を取るロック順序を一貫させる。
// - 破棄時は mutex のみ解放し、GIL の状態は呼び出し側に委ねる (GIL を保持したまま
//   return する関数で使うため、ここで GIL を解放しない)。
//   condition_variable_any は待機から戻る際にロックを取得済みにするため、破棄時は
//   常に mutex を保持している。
struct GILMutexLock {
 public:
  explicit GILMutexLock(std::mutex& mtx) : mtx_(mtx) { mtx_.lock(); }
  ~GILMutexLock() { mtx_.unlock(); }

  GILMutexLock(const GILMutexLock&) = delete;
  GILMutexLock& operator=(const GILMutexLock&) = delete;
  GILMutexLock(GILMutexLock&&) = delete;
  GILMutexLock& operator=(GILMutexLock&&) = delete;

  void lock() {
    gil_.lock();
    mtx_.lock();
  }
  void unlock() {
    mtx_.unlock();
    gil_.unlock();
  }

 private:
  GILLock gil_;
  std::mutex& mtx_;
};

#endif
