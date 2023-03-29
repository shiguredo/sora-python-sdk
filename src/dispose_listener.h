#ifndef DISPOSE_LISTENER_H_
#define DISPOSE_LISTENER_H_

#include <vector>

class DisposeSubscriber {
 public:
  virtual void PubliserDisposed() = 0;
};

class DisposePublisher {
 public:
  void AddSubscriber(DisposeSubscriber* subscriber) {
    subscribers_.push_back(subscriber);
  }
  void RemoveSubscriber(DisposeSubscriber* subscriber) {
    subscribers_.erase(
        std::remove_if(subscribers_.begin(), subscribers_.end(),
                       [subscriber](const DisposeSubscriber* item) {
                         return item == subscriber;
                       }),
        subscribers_.end());
  }
  virtual void Disposed() {
    for (DisposeSubscriber* subscriber : subscribers_) {
      subscriber->PubliserDisposed();
    }
  }

 private:
  std::vector<DisposeSubscriber*> subscribers_;
};

#endif