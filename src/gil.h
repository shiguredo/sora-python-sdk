#ifndef GIL_H_
#define GIL_H_

#include <Python.h>

// nb::gil_scoped_release は終了処理中（Py_IsInitialized() == false 時）に呼ばれた場合の
// 挙動を考えていないので、自前で用意する
struct gil_scoped_release {
 public:
  gil_scoped_release(const gil_scoped_release&) = delete;
  gil_scoped_release(gil_scoped_release&&) = delete;

  gil_scoped_release() noexcept : state(PyEval_SaveThread()) {
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
  // 最初に lock() が呼ばれると危ないけど、condition_variable_any に使う分には
  // unlock() → lock() の順番になるはず
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

// nb::gil_scoped_acquire は終了処理中（Py_IsInitialized() == false 時）に呼ばれた場合の
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

#endif
