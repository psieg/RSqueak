from rpython.rlib import rbigint

from spyvm import model, error
from spyvm.plugins.plugin import Plugin


SocketPlugin = Plugin()


@SocketPlugin.expose_primitive(unwrap_spec=[rbigint, rbigint, bool])
def primDigitMultiplyNegative(interp, s_frame, rcvr, arg, neg):
    result = rcvr.mul(arg)

