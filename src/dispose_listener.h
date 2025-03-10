#ifndef DISPOSE_LISTENER_H_
#define DISPOSE_LISTENER_H_

#include <vector>

// nonobind
// clang-format off
#include <nanobind/nanobind.h>
// clang-format on
#include <nanobind/intrusive/counter.h>
#include <nanobind/intrusive/ref.h>

namespace nb = nanobind;

/**
 * 実装上の留意点：Sora Python SDK は Sora, AudioSource, VideoSource, Connection, Track など、
 * それぞれを Python で別々で扱うことができるようになっているが実態としては親を破棄すると子が止まる関係性が存在する。
 * これを適切にハンドリングしなければリークを引き起こしてしまうため、破棄された、もしくはされることを通知して、
 * 適切にハンドリングを行うためのクラス DisposeSubscriber, DisposePublisher を用意した。
 */

/**
 * 破棄された通知を受ける DisposeSubscriber です。
 * 
 * これを継承することで、 DisposePublisher から破棄された通知を受け取ることができます。
 */
class DisposeSubscriber {
 public:
  /**
   * Subscribe している Publisher が破棄された際に呼び出される関数です。
   */
  virtual void PublisherDisposed() = 0;
};

/**
 * 破棄された際に DisposeSubscriber に通知を送る DisposePublisher です。
 * 
 * 継承して使うことを想定しています。 1 つのインスタンスで複数ので DisposePublisher に破棄を通知することができます。
 */
class DisposePublisher {
 public:
  // クラスによって、 Disposed を呼ぶタイミングを調整する必要があるためデストラクタでの一律 Disposed 呼び出しは行わない

  /**
   * Subscribe する際に呼ぶ関数です。
   * 
   * @param subscriber Subscribe する DisposeSubscriber
   */
  virtual void AddSubscriber(DisposeSubscriber* subscriber) {
    subscribers_.push_back(subscriber);
  }
  /**
   * Subscribe を解除する際に呼ぶ関数です。
   * 
   * @param subscriber Subscribe を解除する DisposeSubscriber
   */
  virtual void RemoveSubscriber(DisposeSubscriber* subscriber) {
    subscribers_.erase(
        std::remove_if(subscribers_.begin(), subscribers_.end(),
                       [subscriber](const DisposeSubscriber* item) {
                         return item == subscriber;
                       }),
        subscribers_.end());
  }
  /**
   * Subscriber に破棄されたことを通知する際に呼ぶ関数です。
   * 
   * TODO(tnoho): 役割的に protected にして良いのでは。
   */
  virtual void Disposed() {
    for (DisposeSubscriber* subscriber : subscribers_) {
      subscriber->PublisherDisposed();
    }
  }

 private:
  std::vector<DisposeSubscriber*> subscribers_;
};

class CountedPublisher : public DisposePublisher, public nb::intrusive_base {
 public:
  void AddSubscriber(DisposeSubscriber* subscriber) override {
    inc_ref();
    DisposePublisher::AddSubscriber(subscriber);
  }
  void RemoveSubscriber(DisposeSubscriber* subscriber) override {
    DisposePublisher::RemoveSubscriber(subscriber);
    dec_ref();
  }
};

#endif