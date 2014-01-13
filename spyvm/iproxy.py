from spyvm.system import IS_64BIT

if not IS_64BIT:
    from spyvm import interpreter_proxy
    IProxy = interpreter_proxy._InterpreterProxy()
else:
    from spyvm.error import PrimitiveFailedError
    class _InterpreterProxy():
        def call(self, signature, interp, s_frame, argcount, s_method):
            raise PrimitiveFailedError
    IProxy = _InterpreterProxy()
