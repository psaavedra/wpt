'use strict';

const SmsTest = (() => {

  class MockSmsReceiver {

    constructor() {
      this.bindingSet_ = new mojo.BindingSet(blink.mojom.SmsReceiver);

      this.interceptor_ = new MojoInterfaceInterceptor(
          blink.mojom.SmsReceiver.name)

      this.interceptor_.oninterfacerequest = (e) => {
        this.bindingSet_.addBinding(this, e.handle);
      }
      this.interceptor_.start();

      this.returnValues_ = {};
    }

    receive(timeout) {
      let call = this.returnValues_.receive ?
          this.returnValues_.receive.shift() : null;
      if (!call) {
        throw new Error("Unexpected call.");
      }
      return Promise.resolve(call);
    }

    pushReturnValuesForTesting(callName, value) {
      this.returnValues_[callName] = this.returnValues_[callName] || [];
      this.returnValues_[callName].push(value);
      return this;
    }

  }

  const mockSmsReceiver = new MockSmsReceiver();

  class SmsTestChromium {
    constructor() {
      Object.freeze(this); // Make it immutable.
    }

    setReturnValues(values) {
      var x;
      for (x in values) {
        mockSmsReceiver.pushReturnValuesForTesting('receive', values[x]);
      }
    }
  }

  return SmsTestChromium;
})();
