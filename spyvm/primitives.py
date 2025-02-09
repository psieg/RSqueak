import os
import inspect
import math
import operator
from spyvm import model, model_display, storage_contexts, error, constants, display
from spyvm.error import PrimitiveFailedError, PrimitiveNotYetWrittenError
from spyvm import wrapper

from rpython.rlib import rarithmetic, rfloat, unroll, jit, objectmodel

def assert_class(interp, w_obj, w_class):
    if not w_obj.getclass(interp.space).is_same_object(w_class):
        raise PrimitiveFailedError()

def assert_bounds(n0, minimum, maximum):
    if not minimum <= n0 < maximum:
        raise PrimitiveFailedError()

def assert_valid_index(space, n0, w_obj):
    if not 0 <= n0 < w_obj.varsize():
        raise PrimitiveFailedError()
    # return the index, since from here on the annotator knows that
    # n0 cannot be negative
    return n0

def assert_pointers(w_obj):
    if not isinstance(w_obj, model.W_PointersObject):
        raise PrimitiveFailedError
    return w_obj

# ___________________________________________________________________________
# Primitive table: it is filled in at initialization time with the
# primitive functions.  Each primitive function takes two
# arguments, an interp and an argument_count
# completes, and returns a result, or throws a PrimitiveFailedError.
def make_failing(code):
    def raise_failing_default(interp, s_frame, argument_count, w_method=None):
        raise PrimitiveFailedError
    return raise_failing_default

# Squeak has primitives all the way up to 575
# So all optional primitives will default to the bytecode implementation
prim_table = [make_failing(i) for i in range(576)]

class PrimitiveHolder(object):
    _immutable_fields_ = ["prim_table[*]"]

prim_holder = PrimitiveHolder()
prim_holder.prim_table = prim_table
# clean up namespace:
del i
prim_table_implemented_only = []

# indicates that what is pushed is an index1, but it is unwrapped and
# converted to an index0
index1_0 = object()
char = object()
pos_32bit_int = object()

def expose_primitive(code, unwrap_spec=None, no_result=False,
                    result_is_new_frame=False, may_context_switch=True,
                    clean_stack=True, compiled_method=False):
    # heuristics to give it a nice name
    name = None
    for key, value in globals().iteritems():
        if isinstance(value, int) and value == code and key == key.upper():
            if name is not None:
                # refusing to guess
                name = "unknown"
            else:
                name = key

    def decorator(func):
        assert code not in prim_table
        func.func_name = "prim_" + name

        wrapped = wrap_primitive(
            unwrap_spec=unwrap_spec, no_result=no_result,
            result_is_new_frame=result_is_new_frame, may_context_switch=may_context_switch,
            clean_stack=clean_stack, compiled_method=compiled_method
        )(func)
        wrapped.func_name = "wrap_prim_" + name
        prim_table[code] = wrapped
        prim_table_implemented_only.append((code, wrapped))
        return func
    return decorator


def wrap_primitive(unwrap_spec=None, no_result=False,
                   result_is_new_frame=False, may_context_switch=True,
                   clean_stack=True, compiled_method=False):
    # some serious magic, don't look
    from rpython.rlib.unroll import unrolling_iterable

    assert not (no_result and result_is_new_frame)
    assert may_context_switch or result_is_new_frame

    # Because methods always have a receiver, an unwrap_spec of [] is a bug
    assert unwrap_spec is None or unwrap_spec

    def decorator(func):
        if unwrap_spec is None:
            def wrapped(interp, s_frame, argument_count_m1, w_method=None):
                if compiled_method:
                    result = func(interp, s_frame, argument_count_m1, w_method)
                else:
                    result = func(interp, s_frame, argument_count_m1)
                if result_is_new_frame:
                    return interp.stack_frame(result, s_frame, may_context_switch)
                if not no_result:
                    assert result is not None
                    s_frame.push(result)
        else:
            len_unwrap_spec = len(unwrap_spec)
            assert len_unwrap_spec + 2 == len(inspect.getargspec(func)[0]), "wrong number of arguments"
            unrolling_unwrap_spec = unrolling_iterable(enumerate(unwrap_spec))
            def wrapped(interp, s_frame, argument_count_m1, w_method=None):
                argument_count = argument_count_m1 + 1 # to account for the rcvr
                assert argument_count == len_unwrap_spec
                if s_frame.stackdepth() < len_unwrap_spec:
                    # XXX shouldn't this be a crash instead?
                    raise PrimitiveFailedError()
                args = ()
                for i, spec in unrolling_unwrap_spec:
                    index = len_unwrap_spec - 1 - i
                    w_arg = s_frame.peek(index)
                    if spec is int:
                        args += (interp.space.unwrap_int(w_arg), )
                    elif spec is pos_32bit_int:
                        args += (interp.space.unwrap_positive_32bit_int(w_arg),)
                    elif spec is index1_0:
                        args += (interp.space.unwrap_int(w_arg)-1, )
                    elif spec is float:
                        args += (interp.space.unwrap_float(w_arg), )
                    elif spec is object:
                        assert isinstance(w_arg, model.W_Object)
                        args += (w_arg, )
                    elif spec is str:
                        assert isinstance(w_arg, model.W_BytesObject)
                        args += (w_arg.as_string(), )
                    elif spec is list:
                        assert isinstance(w_arg, model.W_PointersObject)
                        args += (interp.space.unwrap_array(w_arg), )
                    elif spec is char:
                        args += (unwrap_char(w_arg), )
                    elif spec is bool:
                        args += (interp.space.w_true is w_arg, )
                    else:
                        raise NotImplementedError(
                            "unknown unwrap_spec %s" % (spec, ))
                if result_is_new_frame:
                    s_new_frame = func(interp, s_frame, *args)
                    # After calling primitive, reload context-shadow in case it
                    # needs to be updated
                    if clean_stack:
                        # happens only if no exception occurs!
                        s_frame.pop_n(len_unwrap_spec)
                    return interp.stack_frame(s_new_frame, s_frame, may_context_switch)
                else:
                    w_result = func(interp, s_frame, *args)
                    # After calling primitive, reload context-shadow in case it
                    # needs to be updated
                    if clean_stack:
                        # happens only if no exception occurs!
                        s_frame.pop_n(len_unwrap_spec)
                    if not no_result:
                        assert w_result is not None
                        assert isinstance(w_result, model.W_Object)
                        s_frame.push(w_result)
        return wrapped
    return decorator

# ___________________________________________________________________________
# SmallInteger Primitives


ADD         = 1
SUBTRACT    = 2
MULTIPLY    = 9
DIVIDE      = 10
MOD         = 11
DIV         = 12
QUO         = 13
BIT_AND     = 14
BIT_OR      = 15
BIT_XOR     = 16
BIT_SHIFT   = 17

math_ops = {
    ADD: operator.add,
    SUBTRACT: operator.sub,
    MULTIPLY: operator.mul,
    }
for (code,op) in math_ops.items():
    def make_func(op):
        @expose_primitive(code, unwrap_spec=[int, int])
        def func(interp, s_frame, receiver, argument):
            try:
                res = rarithmetic.ovfcheck(op(receiver, argument))
            except OverflowError:
                raise PrimitiveFailedError()
            return interp.space.wrap_int(res)
    make_func(op)

bitwise_binary_ops = {
    BIT_AND: operator.and_,
    BIT_OR: operator.or_,
    BIT_XOR: operator.xor,
    }
for (code,op) in bitwise_binary_ops.items():
    def make_func(op):
        @expose_primitive(code, unwrap_spec=[pos_32bit_int, pos_32bit_int])
        def func(interp, s_frame, receiver, argument):
            res = op(receiver, argument)
            return interp.space.wrap_positive_32bit_int(rarithmetic.intmask(res))
    make_func(op)

# #/ -- return the result of a division, only succeed if the division is exact
@expose_primitive(DIVIDE, unwrap_spec=[int, int])
def func(interp, s_frame, receiver, argument):
    if argument == 0:
        raise PrimitiveFailedError()
    if receiver % argument != 0:
        raise PrimitiveFailedError()
    return interp.space.wrap_int(receiver // argument)

# #\\ -- return the remainder of a division
@expose_primitive(MOD, unwrap_spec=[int, int])
def func(interp, s_frame, receiver, argument):
    if argument == 0:
        raise PrimitiveFailedError()
    return interp.space.wrap_int(receiver % argument)

# #// -- return the result of a division, rounded towards negative infinity
@expose_primitive(DIV, unwrap_spec=[int, int])
def func(interp, s_frame, receiver, argument):
    if argument == 0:
        raise PrimitiveFailedError()
    return interp.space.wrap_int(receiver // argument)

# #// -- return the result of a division, rounded towards negative infinite
@expose_primitive(QUO, unwrap_spec=[int, int])
def func(interp, s_frame, receiver, argument):
    if argument == 0:
        raise PrimitiveFailedError()
    res = receiver // argument
    # see http://python-history.blogspot.de/2010/08/why-pythons-integer-division-floors.html
    if res < 0 and not abs(receiver) == abs(argument):
        res = res + 1
    return interp.space.wrap_int(res)

# #bitShift: -- return the shifted value
@expose_primitive(BIT_SHIFT, unwrap_spec=[object, int])
def func(interp, s_frame, receiver, argument):
    from rpython.rlib.rarithmetic import LONG_BIT
    if -LONG_BIT < argument < LONG_BIT:
        # overflow-checking done in lshift implementations
        if argument > 0:
            return receiver.lshift(interp.space, argument)
        else:
            return receiver.rshift(interp.space, -argument)
    else:
        raise PrimitiveFailedError()

# ___________________________________________________________________________
# Float Primitives

_FLOAT_OFFSET = 40
SMALLINT_AS_FLOAT = 40
FLOAT_ADD = 41
FLOAT_SUBTRACT = 42
# NB: 43 ... 48 are implemented above
FLOAT_MULTIPLY = 49
FLOAT_DIVIDE = 50
FLOAT_TRUNCATED = 51
# OPTIONAL: 52, 53
FLOAT_TIMES_TWO_POWER = 54
FLOAT_SQUARE_ROOT = 55
FLOAT_SIN = 56
FLOAT_ARCTAN = 57
FLOAT_LOG_N = 58
FLOAT_EXP = 59

@expose_primitive(SMALLINT_AS_FLOAT, unwrap_spec=[int])
def func(interp, s_frame, i):
    return interp.space.wrap_float(float(i))

math_ops = {
    FLOAT_ADD: operator.add,
    FLOAT_SUBTRACT: operator.sub,
    FLOAT_MULTIPLY: operator.mul,
    FLOAT_DIVIDE: operator.div,
    }
for (code,op) in math_ops.items():
    def make_func(op):
        @expose_primitive(code, unwrap_spec=[float, float])
        def func(interp, s_frame, v1, v2):
            w_res = interp.space.wrap_float(op(v1, v2))
            return w_res
    make_func(op)

@expose_primitive(FLOAT_TRUNCATED, unwrap_spec=[float])
def func(interp, s_frame, f):
    try:
        return interp.space.wrap_int(rarithmetic.ovfcheck_float_to_int(f))
    except OverflowError:
        raise PrimitiveFailedError

@expose_primitive(FLOAT_TIMES_TWO_POWER, unwrap_spec=[float, int])
def func(interp, s_frame, rcvr, arg):
    from rpython.rlib.rfloat import INFINITY
    # http://www.python.org/dev/peps/pep-0754/
    try:
        return interp.space.wrap_float(math.ldexp(rcvr, arg))
    except OverflowError:
        if rcvr >= 0.0:
            return model.W_Float(INFINITY)
        else:
            return model.W_Float(-INFINITY)

@expose_primitive(FLOAT_SQUARE_ROOT, unwrap_spec=[float])
def func(interp, s_frame, f):
    if f < 0.0:
        raise PrimitiveFailedError
    w_res = interp.space.wrap_float(math.sqrt(f))
    return w_res

@expose_primitive(FLOAT_SIN, unwrap_spec=[float])
def func(interp, s_frame, f):
    try:
        return interp.space.wrap_float(math.sin(f))
    except ValueError:
        return interp.space.wrap_float(rfloat.NAN)

@expose_primitive(FLOAT_ARCTAN, unwrap_spec=[float])
def func(interp, s_frame, f):
    w_res = interp.space.wrap_float(math.atan(f))
    return w_res

@expose_primitive(FLOAT_LOG_N, unwrap_spec=[float])
def func(interp, s_frame, f):
    if f == 0:
        res = -rfloat.INFINITY
    elif f < 0:
        res = rfloat.NAN
    else:
        res = math.log(f)
    return interp.space.wrap_float(res)

@expose_primitive(FLOAT_EXP, unwrap_spec=[float])
def func(interp, s_frame, f):
    try:
        return interp.space.wrap_float(math.exp(f))
    except OverflowError:
        return interp.space.wrap_float(rfloat.INFINITY)

MAKE_POINT = 18

@expose_primitive(MAKE_POINT, unwrap_spec=[int, int])
def func(interp, s_frame, x, y):
    w_res = interp.space.w_Point.as_class_get_shadow(interp.space).new(2)
    point = wrapper.PointWrapper(interp.space, w_res)
    point.store_x(x)
    point.store_y(y)
    return w_res


# ___________________________________________________________________________
# Failure

FAIL = 19

def get_string(w_obj):
    if isinstance(w_obj, model.W_BytesObject):
        return w_obj.as_string()
    return w_obj.as_repr_string()

def exitFromHeadlessExecution(s_frame, selector="", w_message=None):
    if not objectmodel.we_are_translated():
        import pdb; pdb.set_trace()
    print "== Receiver: %s" % s_frame.w_receiver().as_repr_string()
    if isinstance(w_message, model.W_PointersObject):
        fields = w_message.fetch_all(s_frame.space)
        if len(fields) >= 1:
            print "== Selector: %s" % get_string(fields[0])
        if len(fields) >= 2:
            w_args = fields[1]
            if isinstance(w_args, model.W_PointersObject):
                arg_strings = [ get_string(w_arg) for w_arg in w_args.fetch_all(s_frame.space) ]
                if len(arg_strings) > 0:
                    print "== Arguments: %s" % ', '.join(arg_strings)
    print "== Smalltalk Stack:%s" % s_frame.print_stack()
    if selector == "":
        selector = s_frame.w_method().lookup_selector
    raise error.Exit("Unhandled %s in headless mode." % selector)

@expose_primitive(FAIL)
def func(interp, s_frame, argcount):
    if interp.space.headless.is_set():
        w_message = None
        if s_frame.w_method().lookup_selector == 'doesNotUnderstand:':
            w_arguments = s_frame.w_arguments()
            if len(w_arguments) >= 1:
                w_message = w_arguments[0]
        exitFromHeadlessExecution(s_frame, w_message=w_message)
    raise PrimitiveFailedError()

# ___________________________________________________________________________
# Subscript and Stream Primitives

AT = 60
AT_PUT = 61
SIZE = 62
STRING_AT = 63
STRING_AT_PUT = 64

@expose_primitive(AT, unwrap_spec=[object, index1_0])
def func(interp, s_frame, w_obj, n0):
    n0 = assert_valid_index(interp.space, n0, w_obj)
    return w_obj.at0(interp.space, n0)

@expose_primitive(AT_PUT, unwrap_spec=[object, index1_0, object])
def func(interp, s_frame, w_obj, n0, w_val):
    n0 = assert_valid_index(interp.space, n0, w_obj)
    w_obj.atput0(interp.space, n0, w_val)
    return w_val

@expose_primitive(SIZE, unwrap_spec=[object])
def func(interp, s_frame, w_obj):
    if not w_obj.class_shadow(interp.space).isvariable():
        raise PrimitiveFailedError()
    return interp.space.wrap_int(w_obj.varsize())

@expose_primitive(STRING_AT, unwrap_spec=[object, index1_0])
def func(interp, s_frame, w_obj, n0):
    n0 = assert_valid_index(interp.space, n0, w_obj)
    # XXX I am not sure this is correct, but it un-breaks translation:
    # make sure that getbyte is only performed on W_BytesObjects
    if not isinstance(w_obj, model.W_BytesObject):
        raise PrimitiveFailedError
    return interp.space.wrap_char(w_obj.getchar(n0))

@expose_primitive(STRING_AT_PUT, unwrap_spec=[object, index1_0, object])
def func(interp, s_frame, w_obj, n0, w_val):
    val = interp.space.unwrap_char(w_val)
    n0 = assert_valid_index(interp.space, n0, w_obj)
    if not (isinstance(w_obj, model.W_CompiledMethod) or
            isinstance(w_obj, model.W_BytesObject)):
        raise PrimitiveFailedError()
    w_obj.setchar(n0, val)
    return w_val

# ___________________________________________________________________________
# Stream Primitives

NEXT = 65
NEXT_PUT = 66
AT_END = 67

# ___________________________________________________________________________
# Storage Management Primitives

OBJECT_AT = 68
OBJECT_AT_PUT = 69
NEW = 70
NEW_WITH_ARG = 71
ARRAY_BECOME_ONE_WAY = 72     # Blue Book: primitiveBecome
INST_VAR_AT = 73
INST_VAR_AT_PUT = 74
AS_OOP = 75
STORE_STACKP = 76             # Blue Book: primitiveAsObject
SOME_INSTANCE = 77
NEXT_INSTANCE = 78
NEW_METHOD = 79

@expose_primitive(OBJECT_AT, unwrap_spec=[object, index1_0])
def func(interp, s_frame, w_rcvr, n0):
    if not isinstance(w_rcvr, model.W_CompiledMethod):
        raise PrimitiveFailedError()
    return w_rcvr.literalat0(interp.space, n0)

@expose_primitive(OBJECT_AT_PUT, unwrap_spec=[object, index1_0, object])
def func(interp, s_frame, w_rcvr, n0, w_value):
    if not isinstance(w_rcvr, model.W_CompiledMethod):
        raise PrimitiveFailedError()
    #assert_bounds(n0, 0, len(w_rcvr.literals))
    w_rcvr.literalatput0(interp.space, n0, w_value)
    return w_value

@expose_primitive(NEW, unwrap_spec=[object])
def func(interp, s_frame, w_cls):
    w_cls = assert_pointers(w_cls)
    s_class = w_cls.as_class_get_shadow(interp.space)
    if s_class.isvariable():
        raise PrimitiveFailedError()
    return s_class.new()

@expose_primitive(NEW_WITH_ARG, unwrap_spec=[object, int])
def func(interp, s_frame, w_cls, size):
    w_cls = assert_pointers(w_cls)
    s_class = w_cls.as_class_get_shadow(interp.space)
    if not s_class.isvariable() and size != 0:
        raise PrimitiveFailedError()
    try:
        return s_class.new(size)
    except MemoryError:
        raise PrimitiveFailedError

@expose_primitive(ARRAY_BECOME_ONE_WAY, unwrap_spec=[object, object])
def func(interp, s_frame, w_obj1, w_obj2):
    raise PrimitiveNotYetWrittenError

@expose_primitive(INST_VAR_AT, unwrap_spec=[object, index1_0])
def func(interp, s_frame, w_rcvr, n0):
    "Fetches a fixed field from the object, and fails otherwise"
    s_class = w_rcvr.class_shadow(interp.space)
    assert_bounds(n0, 0, s_class.instsize())
    w_cls = assert_pointers(w_rcvr)
    return w_rcvr.fetch(interp.space, n0)

@expose_primitive(INST_VAR_AT_PUT, unwrap_spec=[object, index1_0, object])
def func(interp, s_frame, w_rcvr, n0, w_value):
    "Stores a value into a fixed field from the object, and fails otherwise"
    s_class = w_rcvr.class_shadow(interp.space)
    assert_bounds(n0, 0, s_class.instsize())
    w_rcvr = assert_pointers(w_rcvr)
    w_rcvr.store(interp.space, n0, w_value)
    return w_value

@expose_primitive(AS_OOP, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    if isinstance(w_rcvr, model.W_SmallInteger):
        raise PrimitiveFailedError()
    return interp.space.wrap_int(w_rcvr.gethash())

@expose_primitive(STORE_STACKP, unwrap_spec=[object, int])
def func(interp, s_frame, w_frame, stackp):
    assert stackp >= 0
    w_frame = assert_pointers(w_frame)
    w_frame.store(interp.space, constants.CTXPART_STACKP_INDEX, interp.space.wrap_int(stackp))
    return w_frame


def stm_enabled():
    """NOT RPYTHON"""
    from rpython.rlib import rgc
    return hasattr(rgc, "stm_is_enabled") and rgc.stm_is_enabled()
if stm_enabled():
    def get_instances_array(space, s_frame, w_class):
        return []
else:
    def get_instances_array(space, s_frame, w_class):
        # This primitive returns some instance of the class on the stack.
        # Not sure quite how to do this; maintain a weak list of all
        # existing instances or something?
        match_w = s_frame.instances_array(w_class)
        if match_w is None:
            match_w = []
            from rpython.rlib import rgc

            roots = [gcref for gcref in rgc.get_rpy_roots() if gcref]
            pending = roots[:]
            while pending:
                gcref = pending.pop()
                if not rgc.get_gcflag_extra(gcref):
                    rgc.toggle_gcflag_extra(gcref)
                    w_obj = rgc.try_cast_gcref_to_instance(model.W_Object, gcref)
                    if (w_obj is not None and w_obj.has_class()
                        and w_obj.getclass(space) is w_class):
                        match_w.append(w_obj)
                    pending.extend(rgc.get_rpy_referents(gcref))

            while roots:
                gcref = roots.pop()
                if rgc.get_gcflag_extra(gcref):
                    rgc.toggle_gcflag_extra(gcref)
                    roots.extend(rgc.get_rpy_referents(gcref))
            s_frame.store_instances_array(w_class, match_w)
        return match_w

@expose_primitive(SOME_INSTANCE, unwrap_spec=[object])
def func(interp, s_frame, w_class):
    match_w = get_instances_array(interp.space, s_frame, w_class)
    try:
        return match_w[0]
    except IndexError:
        raise PrimitiveFailedError()

def next_instance(space, list_of_objects, w_obj):
    retval = None
    try:
        idx = list_of_objects.index(w_obj)
    except ValueError:
        idx = -1
    try:
        retval = list_of_objects[idx + 1]
    except IndexError:
        raise PrimitiveFailedError()
    # just in case, that one of the objects in the list changes its class
    if retval.getclass(space).is_same_object(w_obj.getclass(space)):
        return retval
    else:
        list_of_objects.pop(idx + 1)
        return next_instance(space, list_of_objects, w_obj)

@expose_primitive(NEXT_INSTANCE, unwrap_spec=[object])
def func(interp, s_frame, w_obj):
    # This primitive is used to iterate through all instances of a class:
    # it returns the "next" instance after w_obj.
    return next_instance(
        interp.space,
        get_instances_array(interp.space, s_frame, w_obj.getclass(interp.space)),
        w_obj
    )

@expose_primitive(NEW_METHOD, unwrap_spec=[object, int, int])
def func(interp, s_frame, w_class, bytecount, header):
    # We ignore w_class because W_CompiledMethod is special
    return model.W_CompiledMethod(interp.space, bytecount, header)

# ___________________________________________________________________________
# I/O Primitives

MOUSE_POINT = 90
TEST_DISPLAY_DEPTH = 91
SET_DISPLAY_MODE = 92
INPUT_SEMAPHORE = 93
GET_NEXT_EVENT = 94
INPUT_WORD = 95
BITBLT_COPY_BITS = 96
SNAPSHOT = 97
STORE_IMAGE_SEGMENT = 98
LOAD_IMAGE_SEGMENT = 99
PERFORM_IN_SUPERCLASS = 100
BE_CURSOR = 101
BE_DISPLAY = 102
SCAN_CHARACTERS = 103
OBSOLETE_INDEXED = 104 # also 96
STRING_REPLACE = 105
SCREEN_SIZE = 106
MOUSE_BUTTONS = 107
KBD_NEXT = 108
KBD_PEEK = 109

@expose_primitive(MOUSE_POINT, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    x, y = interp.space.display().mouse_point()
    w_point = model.W_PointersObject(interp.space, interp.space.w_Point, 2)
    w_point.store(interp.space, 0, interp.space.wrap_int(x))
    w_point.store(interp.space, 1, interp.space.wrap_int(y))
    return w_point

@jit.unroll_safe
@jit.look_inside
@expose_primitive(GET_NEXT_EVENT, unwrap_spec=[object, object])
def func(interp, s_frame, w_rcvr, w_into):
    if not interp.evented:
        raise PrimitiveFailedError()
    ary = interp.space.display().get_next_event(time=interp.time_now())
    for i in range(8):
        w_into.store(interp.space, i, interp.space.wrap_int(ary[i]))
    # XXX - hack
    if ary[0] == display.WindowEventMetricChange and ary[4] > 0 and ary[5] > 0:
        if interp.image:
            interp.image.lastWindowSize = ((ary[4] & 0xffff) << 16) | (ary[5] & 0xffff)
    return w_rcvr

@expose_primitive(BITBLT_COPY_BITS, clean_stack=False, no_result=False, compiled_method=True)
def func(interp, s_frame, argcount, w_method):
    from spyvm.interpreter import Return
    w_rcvr = s_frame.peek(0)
    try:
        s_frame._sendSelfSelector(interp.image.w_simulateCopyBits, 0, interp)
    except Return:
        w_dest_form = w_rcvr.fetch(interp.space, 0)
        w_display = interp.space.objtable['w_display']
        if w_dest_form.is_same_object(w_display):
            w_bitmap = w_display.fetch(interp.space, 0)
            assert isinstance(w_bitmap, model_display.W_DisplayBitmap)
            w_bitmap.flush_to_screen()
        return w_rcvr
    except error.MethodNotFound:
        from spyvm.plugins.bitblt import BitBltPlugin
        BitBltPlugin.call("primitiveCopyBits", interp, s_frame, argcount, w_method)
        return w_rcvr

@expose_primitive(BE_CURSOR)
def func(interp, s_frame, argcount):
    if not (0 <= argcount <= 1):
        raise PrimitiveFailedError()
    w_rcvr = s_frame.peek(argcount)
    mask_words = None
    if argcount == 1:
        # TODO: use mask
        w_mask = s_frame.peek(0)
        if isinstance(w_mask, model.W_WordsObject):
            mask_words = w_mask.words
        elif isinstance(w_mask, model.W_PointersObject):
            # mask is a form object
            w_contents = w_mask.fetch(interp.space, 0)
            if isinstance(w_contents, model.W_WordsObject):
                mask_words = w_contents.words
            else:
                raise PrimitiveFailedError
        else:
            raise PrimitiveFailedError()
    w_bitmap = w_rcvr.fetch(interp.space, 0)
    if not isinstance(w_bitmap, model.W_WordsObject):
        raise PrimitiveFailedError()
    width = interp.space.unwrap_int(w_rcvr.fetch(interp.space, 1))
    height = interp.space.unwrap_int(w_rcvr.fetch(interp.space, 2))
    depth = interp.space.unwrap_int(w_rcvr.fetch(interp.space, 3))
    hotpt = wrapper.PointWrapper(interp.space, w_rcvr.fetch(interp.space, 4))
    if not interp.image.version.is_modern:
        display.SDLCursor.set(
            w_bitmap.words,
            width,
            height,
            hotpt.x(),
            hotpt.y(),
            mask_words=mask_words
        )
    else:
        # TODO: Implement
        pass

    interp.space.objtable['w_cursor'] = w_rcvr
    return w_rcvr

@expose_primitive(BE_DISPLAY, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    if interp.space.headless.is_set():
        exitFromHeadlessExecution(s_frame)
    if not isinstance(w_rcvr, model.W_PointersObject) or w_rcvr.size() < 4:
        raise PrimitiveFailedError

    old_display = interp.space.objtable['w_display']
    if isinstance(old_display, model_display.W_DisplayBitmap):
        old_display.relinquish_display()
    interp.space.objtable['w_display'] = w_rcvr

    # TODO: figure out whether we should decide the width an report it in the SCREEN_SIZE primitive
    form = wrapper.FormWrapper(interp.space, w_rcvr)
    form.take_over_display()
    w_display_bitmap = form.get_display_bitmap()
    w_display_bitmap.take_over_display()
    w_display_bitmap.flush_to_screen()

    if interp.image:
        interp.image.lastWindowSize = (form.width() << 16) + form.height()
    return w_rcvr

@expose_primitive(STRING_REPLACE, unwrap_spec=[object, index1_0, index1_0, object, index1_0])
def func(interp, s_frame, w_rcvr, start, stop, w_replacement, repStart):
    """replaceFrom: start to: stop with: replacement startingAt: repStart
    Primitive. This destructively replaces elements from start to stop in the
    receiver starting at index, repStart, in the collection, replacement. Answer
    the receiver. Range checks are performed in the primitive only. Essential
    for Pharo Candle Symbols.
    | index repOff |
    repOff := repStart - start.
    index := start - 1.
    [(index := index + 1) <= stop]
        whileTrue: [self at: index put: (replacement at: repOff + index)]"""
    if (start < 0 or start - 1 > stop or repStart < 0):
        raise PrimitiveFailedError()
    # This test deliberately test for equal W_Object class. The Smalltalk classes
    # might be different (e.g. Symbol and ByteString)
    if w_rcvr.__class__ is not w_replacement.__class__:
        raise PrimitiveFailedError
    if (w_rcvr.size() - w_rcvr.instsize() <= stop
            or w_replacement.size() - w_replacement.instsize() <= repStart + (stop - start)):
        raise PrimitiveFailedError()
    repOff = repStart - start
    for i0 in range(start, stop + 1):
        w_rcvr.atput0(interp.space, i0, w_replacement.at0(interp.space, repOff + i0))
    return w_rcvr

@expose_primitive(SCREEN_SIZE, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    # We need to have the indirection via interp.image, because when the image
    # is saved, the display form size is always reduced to 240@120.
    if not interp.image:
        raise PrimitiveFailedError
    w_res = interp.space.w_Point.as_class_get_shadow(interp.space).new(2)
    point = wrapper.PointWrapper(interp.space, w_res)
    point.store_x((interp.image.lastWindowSize >> 16) & 0xffff)
    point.store_y(interp.image.lastWindowSize & 0xffff)
    return w_res

@expose_primitive(MOUSE_BUTTONS, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    btn = interp.space.display().mouse_button()
    return interp.space.wrap_int(btn)

@expose_primitive(KBD_NEXT, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    code = interp.space.display().next_keycode()
    if code & 0xFF == 0:
        return interp.space.w_nil
    else:
        return interp.space.wrap_int(code)

@expose_primitive(KBD_PEEK, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    code = interp.space.display().peek_keycode()
    if code & 0xFF == 0:
        return interp.space.w_nil
    else:
        return interp.space.wrap_int(code)


# ___________________________________________________________________________
# Control Primitives

EQUIVALENT = 110
CLASS = 111
BYTES_LEFT = 112
QUIT = 113
EXIT_TO_DEBUGGER = 114
CHANGE_CLASS = 115      # Blue Book: primitiveOopsLeft
COMPILED_METHOD_FLUSH_CACHE = 116
EXTERNAL_CALL = 117
SYMBOL_FLUSH_CACHE = 119

@expose_primitive(EQUIVALENT, unwrap_spec=[object, object])
def func(interp, s_frame, w_arg, w_rcvr):
    return interp.space.wrap_bool(w_arg.is_same_object(w_rcvr))

@expose_primitive(CLASS, unwrap_spec=[object])
def func(interp, s_frame, w_obj):
    return w_obj.getclass(interp.space)

@expose_primitive(BYTES_LEFT, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    raise PrimitiveNotYetWrittenError()

@expose_primitive(QUIT, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    from spyvm.error import Exit
    raise Exit('Quit-Primitive called')

@expose_primitive(EXIT_TO_DEBUGGER, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    if interp.space.headless.is_set():
        exitFromHeadlessExecution(s_frame, "EXIT_TO_DEBUGGER")
    raise PrimitiveNotYetWrittenError()

@expose_primitive(CHANGE_CLASS, unwrap_spec=[object, object], no_result=True)
def func(interp, s_frame, w_arg, w_rcvr):
    w_arg_class = w_arg.getclass(interp.space)
    w_rcvr_class = w_rcvr.getclass(interp.space)

    # We should fail if:

    # 1. Rcvr or arg are SmallIntegers
    # XXX this is wrong too
    if (w_arg_class.is_same_object(interp.space.w_SmallInteger) or
        w_rcvr_class.is_same_object(interp.space.w_SmallInteger)):
        raise PrimitiveFailedError()

    # 2. Rcvr is an instance of a compact class and argument isn't
    # or vice versa XXX we don't have to fail here, but for squeak it's a problem

    # 3. Format of rcvr is different from format of argument
    raise PrimitiveNotYetWrittenError()     # XXX needs to work in the shadows
    if w_arg_class.format != w_rcvr_class.format:
        raise PrimitiveFailedError()

    # Fail when argument class is fixed and rcvr's size differs from the
    # size of an instance of the arg
    if w_arg_class.instsize() != w_rcvr_class.instsize():
        raise PrimitiveFailedError()

    w_rcvr.w_class = w_arg_class

@expose_primitive(EXTERNAL_CALL, clean_stack=False, no_result=True, compiled_method=True)
def func(interp, s_frame, argcount, w_method):
    space = interp.space
    w_description = w_method.literalat0(space, 1)
    if not isinstance(w_description, model.W_PointersObject) or w_description.size() < 2:
        raise PrimitiveFailedError
    w_modulename = w_description.at0(space, 0)
    w_functionname = w_description.at0(space, 1)
    if not (isinstance(w_modulename, model.W_BytesObject) and
            isinstance(w_functionname, model.W_BytesObject)):
        raise PrimitiveFailedError
    signature = (w_modulename.as_string(), w_functionname.as_string())

    if signature[0] == 'BitBltPlugin':
        from spyvm.plugins.bitblt import BitBltPlugin
        return BitBltPlugin.call(signature[1], interp, s_frame, argcount, w_method)
    elif signature[0] == "SocketPlugin":
        from spyvm.plugins.socket import SocketPlugin
        return SocketPlugin.call(signature[1], interp, s_frame, argcount, w_method)
    elif signature[0] == "FilePlugin":
        from spyvm.plugins.fileplugin import FilePlugin
        return FilePlugin.call(signature[1], interp, s_frame, argcount, w_method)
    elif signature[0] == "VMDebugging":
        from spyvm.plugins.vmdebugging import DebuggingPlugin
        return DebuggingPlugin.call(signature[1], interp, s_frame, argcount, w_method)
    else:
        raise PrimitiveFailedError

@expose_primitive(COMPILED_METHOD_FLUSH_CACHE, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    if not isinstance(w_rcvr, model.W_CompiledMethod):
        raise PrimitiveFailedError()
    w_class = w_rcvr.compiled_in()
    if w_class:
        w_class = assert_pointers(w_class)
        w_class.as_class_get_shadow(interp.space).flush_method_caches()
    return w_rcvr

@objectmodel.specialize.arg(0)
def walk_gc_references(func, gcrefs):
    from rpython.rlib import rgc
    for gcref in gcrefs:
        if gcref and not rgc.get_gcflag_extra(gcref):
            try:
                rgc.toggle_gcflag_extra(gcref)
                func(gcref)
                walk_gc_references(func, rgc.get_rpy_referents(gcref))
            finally:
                rgc.toggle_gcflag_extra(gcref)

@objectmodel.specialize.arg(0)
def walk_gc_objects(func):
    from rpython.rlib import rgc
    walk_gc_references(func, rgc.get_rpy_roots())

@objectmodel.specialize.arg(0, 1)
def walk_gc_objects_of_type(type, func):
    from rpython.rlib import rgc
    def check_type(gcref):
        w_obj = rgc.try_cast_gcref_to_instance(type, gcref)
        if w_obj:
            func(w_obj)
    walk_gc_objects(check_type)

if not stm_enabled():
    # XXX: We don't have a global symbol cache. Instead, we walk all
    # MethodDictionaryShadow objects and flush them.
    @expose_primitive(SYMBOL_FLUSH_CACHE, unwrap_spec=[object])
    def func(interp, s_frame, w_rcvr):
        # This takes a long time (at least in interpreted mode), and is not really necessary.
        # We are monitoring changes to MethodDictionaries, so there is no need for the image to tell us.
        #walk_gc_objects_of_type(storage_contexts.MethodDictionaryShadow, lambda s_dict: s_dict.flush_method_cache())
        return w_rcvr

# ___________________________________________________________________________
# Miscellaneous Primitives (120-127)
CALLOUT_TO_FFI = 120
IMAGE_NAME = 121
NOOP = 122
VALUE_UNINTERRUPTABLY = 123
LOW_SPACE_SEMAPHORE = 124
SIGNAL_AT_BYTES_LEFT = 125
DEFER_UPDATES = 126
DRAW_RECTANGLE = 127

@expose_primitive(IMAGE_NAME)
def func(interp, s_frame, argument_count):
    if argument_count == 0:
        s_frame.pop()
        return interp.space.wrap_string(interp.space.image_name())
    elif argument_count == 1:
        pass # XXX
    raise PrimitiveFailedError

@expose_primitive(LOW_SPACE_SEMAPHORE, unwrap_spec=[object, object])
def func(interp, s_frame, w_receiver, i):
    # dont know when the space runs out
    return w_receiver

@expose_primitive(SIGNAL_AT_BYTES_LEFT, unwrap_spec=[object, int])
def func(interp, s_frame, w_receiver, i):
    # dont know when the space runs out
    return w_receiver

@expose_primitive(DEFER_UPDATES, unwrap_spec=[object, bool])
def func(interp, s_frame, w_receiver, flag):
    sdldisplay = interp.space.display()
    sdldisplay.defer_updates(flag)
    return w_receiver

@expose_primitive(DRAW_RECTANGLE, unwrap_spec=[object, int, int, int, int])
def func(interp, s_frame, w_rcvr, left, right, top, bottom):
    raise PrimitiveNotYetWrittenError()


# ___________________________________________________________________________
# Squeak Miscellaneous Primitives (128-134)
BECOME = 128
SPECIAL_OBJECTS_ARRAY = 129
FULL_GC = 130
INC_GC = 131
SET_INTERRUPT_KEY = 133
INTERRUPT_SEMAPHORE = 134

@expose_primitive(BECOME, unwrap_spec=[object, object])
def func(interp, s_frame, w_rcvr, w_new):
    if w_rcvr.size() != w_new.size():
        raise PrimitiveFailedError
    w_lefts = []
    w_rights = []
    for i in range(w_rcvr.size()):
        w_left = w_rcvr.at0(interp.space, i)
        w_right = w_new.at0(interp.space, i)
        if w_left.become(w_right):
            w_lefts.append(w_left)
            w_rights.append(w_right)
        else:
            for i in range(len(w_lefts)):
                w_lefts[i].become(w_rights[i])
            raise PrimitiveFailedError()
    return w_rcvr

def fake_bytes_left(interp):
    return interp.space.wrap_int(2**29) # XXX we don't know how to do this :-(

@expose_primitive(SPECIAL_OBJECTS_ARRAY, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    return interp.space.wrap_list(interp.image.special_objects)

@expose_primitive(INC_GC, unwrap_spec=[object])
@expose_primitive(FULL_GC, unwrap_spec=[object])
@jit.dont_look_inside
# def func(interp, s_frame, w_arg): # Squeak pops the arg and ignores it ... go figure
def func(interp, s_frame, w_rcvr):
    from rpython.rlib import rgc
    rgc.collect()
    return fake_bytes_left(interp)

@expose_primitive(SET_INTERRUPT_KEY, unwrap_spec=[object, int])
def func(interp, s_frame, w_rcvr, encoded_key):
    interp.space.display().set_interrupt_key(interp.space, encoded_key)
    return w_rcvr

@expose_primitive(INTERRUPT_SEMAPHORE, unwrap_spec=[object, object])
def func(interp, s_frame, w_rcvr, w_semaphore):
    if w_semaphore.getclass(interp.space).is_same_object(interp.space.w_Semaphore):
        interp.space.objtable['w_interrupt_semaphore'] = w_semaphore
    else:
        interp.space.objtable['w_interrupt_semaphore'] = interp.space.w_nil
    return w_rcvr

#____________________________________________________________________________
# Time Primitives (135 - 137)
MILLISECOND_CLOCK = 135
SIGNAL_AT_MILLISECONDS = 136
SECONDS_CLOCK = 137

@expose_primitive(MILLISECOND_CLOCK, unwrap_spec=[object])
def func(interp, s_frame, w_arg):
    return interp.space.wrap_int(interp.time_now())

@expose_primitive(SIGNAL_AT_MILLISECONDS, unwrap_spec=[object, object, int])
def func(interp, s_frame, w_delay, w_semaphore, timestamp):
    if not w_semaphore.getclass(interp.space).is_same_object(
            interp.space.w_Semaphore):
        interp.space.objtable["w_timerSemaphore"] = interp.space.w_nil
        interp.next_wakeup_tick = timestamp
    else:
        interp.space.objtable["w_timerSemaphore"] = w_semaphore
        interp.next_wakeup_tick = timestamp
    return w_delay



secs_between_1901_and_1970 = rarithmetic.r_uint((69 * 365 + 17) * 24 * 3600)

@expose_primitive(SECONDS_CLOCK, unwrap_spec=[object])
def func(interp, s_frame, w_arg):
    import time
    sec_since_epoch = rarithmetic.r_uint(time.time())
    # XXX: overflow check necessary?
    sec_since_1901 = sec_since_epoch + secs_between_1901_and_1970
    return interp.space.wrap_uint(sec_since_1901)


#____________________________________________________________________________
# Misc Primitives (138 - 149)
BEEP = 140
VM_PATH = 142
SHORT_AT = 143
SHORT_AT_PUT = 144
FILL = 145
CLONE = 148

@expose_primitive(BEEP, unwrap_spec=[object])
def func(interp, s_frame, w_receiver):
    return w_receiver

@expose_primitive(VM_PATH, unwrap_spec=[object])
def func(interp, s_frame, w_receiver):
    return interp.space.wrap_string("%s%s" % (interp.space.executable_path(), os.path.sep))

@expose_primitive(SHORT_AT, unwrap_spec=[object, index1_0])
def func(interp, s_frame, w_receiver, n0):
    if not (isinstance(w_receiver, model.W_BytesObject)
            or isinstance(w_receiver, model.W_WordsObject)):
        raise PrimitiveFailedError
    return w_receiver.short_at0(interp.space, n0)

@expose_primitive(SHORT_AT_PUT, unwrap_spec=[object, index1_0, object])
def func(interp, s_frame, w_receiver, n0, w_value):
    if not (isinstance(w_receiver, model.W_BytesObject)
            or isinstance(w_receiver, model.W_WordsObject)):
        raise PrimitiveFailedError
    return w_receiver.short_atput0(interp.space, n0, w_value)

@expose_primitive(FILL, unwrap_spec=[object, pos_32bit_int])
def func(interp, s_frame, w_arg, new_value):
    space = interp.space
    if isinstance(w_arg, model.W_BytesObject):
        if new_value > 255:
            raise PrimitiveFailedError
        for i in xrange(w_arg.size()):
            w_arg.setchar(i, chr(new_value))
    elif isinstance(w_arg, model.W_WordsObject) or isinstance(w_arg, model_display.W_DisplayBitmap):
        for i in xrange(w_arg.size()):
            w_arg.setword(i, new_value)
    else:
        raise PrimitiveFailedError
    return w_arg

@expose_primitive(CLONE, unwrap_spec=[object])
def func(interp, s_frame, w_arg):
    return w_arg.clone(interp.space)

# ___________________________________________________________________________
# File primitives (150-169)
# (XXX they are obsolete in Squeak and done with a plugin)

FILE_AT_END = 150
FILE_CLOSE = 151
FILE_GET_POSITION = 152
FILE_OPEN = 153
FILE_READ = 154
FILE_SET_POSITION = 155
FILE_DELETE = 156
FILE_SIZE = 157
FILE_WRITE = 158
FILE_RENAME = 159
DIRECTORY_CREATE = 160
DIRECTORY_DELIMITOR = 161
DIRECTORY_LOOKUP = 162
DIRECTORY_DELTE = 163

@expose_primitive(FILE_CLOSE, unwrap_spec=[object, int])
def func(interp, s_frame, w_rcvr, fd):
    try:
        os.close(fd)
    except OSError:
        raise PrimitiveFailedError()
    return w_rcvr

@expose_primitive(FILE_OPEN, unwrap_spec=[object, str, object])
def func(interp, s_frame, w_rcvr, filename, w_writeable_flag):
    if w_writeable_flag.is_same_object(interp.space.w_true):
        mode = os.O_RDWR | os.O_CREAT | os.O_TRUNC
    else:
        mode = os.O_RDONLY
    try:
        fd = os.open(filename, mode, 0666)
    except OSError:
        raise PrimitiveFailedError()
    return interp.space.wrap_int(fd)

@expose_primitive(FILE_WRITE, unwrap_spec=[object, int, str, int, int])
def func(interp, s_frame, w_rcvr, fd, src, start, count):
    start = start - 1
    end = start + count
    if end < 0 or start < 0:
        raise PrimitiveFailedError()
    try:
        os.write(fd, src[start:end])
    except OSError:
        raise PrimitiveFailedError()
    return w_rcvr

@expose_primitive(DIRECTORY_DELIMITOR, unwrap_spec=[object])
def func(interp, s_frame, _):
    return interp.space.wrap_char(os.path.sep)


# ___________________________________________________________________________
# Boolean Primitives

LESSTHAN = 3
GREATERTHAN = 4
LESSOREQUAL = 5
GREATEROREQUAL = 6
EQUAL = 7
NOTEQUAL = 8

FLOAT_LESSTHAN = 43
FLOAT_GREATERTHAN = 44
FLOAT_LESSOREQUAL = 45
FLOAT_GREATEROREQUAL = 46
FLOAT_EQUAL = 47
FLOAT_NOTEQUAL = 48

bool_ops = {
    LESSTHAN: operator.lt,
    GREATERTHAN: operator.gt,
    LESSOREQUAL: operator.le,
    GREATEROREQUAL:operator.ge,
    EQUAL: operator.eq,
    NOTEQUAL: operator.ne
    }
for (code,op) in bool_ops.items():
    def make_func(op):
        @expose_primitive(code, unwrap_spec=[int, int])
        def func(interp, s_frame, v1, v2):
            res = op(v1, v2)
            w_res = interp.space.wrap_bool(res)
            return w_res
    make_func(op)

for (code,op) in bool_ops.items():
    def make_func(op):
        @expose_primitive(code+_FLOAT_OFFSET, unwrap_spec=[float, float])
        def func(interp, s_frame, v1, v2):
            res = op(v1, v2)
            w_res = interp.space.wrap_bool(res)
            return w_res
    make_func(op)

# ___________________________________________________________________________
# Quick Push Const Primitives

PUSH_SELF = 256
PUSH_TRUE = 257
PUSH_FALSE = 258
PUSH_NIL = 259
PUSH_MINUS_ONE = 260
PUSH_ZERO = 261
PUSH_ONE = 262
PUSH_TWO = 263

@expose_primitive(PUSH_SELF, unwrap_spec=[object])
def func(interp, s_frame, w_self):
    # no-op really
    return w_self

def make_push_const_func(code, name):
    @expose_primitive(code, unwrap_spec=[object])
    def func(interp, s_frame, w_ignored):
        return getattr(interp.space, name)
    return func

for (code, name) in [
    (PUSH_TRUE, "w_true"),
    (PUSH_FALSE, "w_false"),
    (PUSH_NIL, "w_nil"),
    (PUSH_MINUS_ONE, "w_minus_one"),
    (PUSH_ZERO, "w_zero"),
    (PUSH_ONE, "w_one"),
    (PUSH_TWO, "w_two"),
    ]:
    make_push_const_func(code, name)

# ___________________________________________________________________________
# Control Primitives

BLOCK_COPY = 80
VALUE = 81
VALUE_WITH_ARGS = 82
PERFORM = 83
PERFORM_WITH_ARGS = 84
SIGNAL = 85
WAIT = 86
RESUME = 87
SUSPEND = 88
FLUSH_CACHE = 89
WITH_ARGS_EXECUTE_METHOD = 188

@expose_primitive(BLOCK_COPY, unwrap_spec=[object, int])
def func(interp, s_frame, w_context, argcnt):

    # From B.B.: If receiver is a MethodContext, then it becomes
    # the new BlockContext's home context.  Otherwise, the home
    # context of the receiver is used for the new BlockContext.
    # Note that in our impl, MethodContext.w_home == self
    w_context = assert_pointers(w_context)
    s_method_context = w_context.as_context_get_shadow(interp.space).s_home()

    # The block bytecodes are stored inline: so we skip past the
    # bytecodes to invoke this primitive to get to them.
    initialip = s_frame.pc() + 2
    s_new_context = storage_contexts.ContextPartShadow.build_block_context(interp.space, s_method_context, argcnt, initialip)
    return s_new_context.w_self()

@expose_primitive(VALUE, result_is_new_frame=True)
def func(interp, s_frame, argument_count):
    # argument_count does NOT include the receiver.
    # This means that for argument_count == 3 the stack looks like:
    #  3      2       1      Top
    #  Rcvr | Arg 0 | Arg1 | Arg 2
    #
    # Validate that we have a block on the stack and that it received
    # the proper number of arguments:
    w_block_ctx = s_frame.peek(argument_count)

    # XXX need to check this since VALUE is called on all sorts of objects.
    if not w_block_ctx.getclass(interp.space).is_same_object(
        interp.space.w_BlockContext):
        raise PrimitiveFailedError()

    w_block_ctx = assert_pointers(w_block_ctx)
    s_block_ctx = w_block_ctx.as_blockcontext_get_shadow(interp.space)

    exp_arg_cnt = s_block_ctx.expected_argument_count()
    if argument_count != exp_arg_cnt: # exp_arg_cnt doesn't count self
        raise PrimitiveFailedError()

    # Initialize the block stack with the arguments that were
    # pushed.  Also pop the receiver.
    block_args = s_frame.pop_and_return_n(exp_arg_cnt)

    # Reset stack of blockcontext to []
    s_block_ctx.reset_stack()
    s_block_ctx.push_all(block_args)

    s_frame.pop()
    s_block_ctx.reset_pc()
    return s_block_ctx

@expose_primitive(VALUE_WITH_ARGS, unwrap_spec=[object, list],
                  result_is_new_frame=True)
def func(interp, s_frame, w_block_ctx, args_w):

    w_block_ctx = assert_pointers(w_block_ctx)
    s_block_ctx = w_block_ctx.as_blockcontext_get_shadow(interp.space)
    exp_arg_cnt = s_block_ctx.expected_argument_count()

    if len(args_w) != exp_arg_cnt:
        raise PrimitiveFailedError()

    # Push all the items from the array
    for i in range(exp_arg_cnt):
        s_block_ctx.push(args_w[i])

    # XXX Check original logic. Image does not test this anyway
    # because falls back to value + internal implementation
    s_block_ctx.reset_pc()
    return s_block_ctx

@expose_primitive(PERFORM)
def func(interp, s_frame, argcount):
    raise PrimitiveFailedError()

@expose_primitive(PERFORM_WITH_ARGS,
                  unwrap_spec=[object, object, list],
                  no_result=True, clean_stack=False)
def func(interp, s_frame, w_rcvr, w_selector, w_arguments):
    s_frame.pop_n(2) # removing our arguments
    return s_frame._sendSelector(w_selector, len(w_arguments), interp, w_rcvr,
                        w_rcvr.class_shadow(interp.space), w_arguments=w_arguments)

@expose_primitive(WITH_ARGS_EXECUTE_METHOD,
    result_is_new_frame=True, unwrap_spec=[object, list, object])
def func(interp, s_frame, w_rcvr, args_w, w_cm):
    if not isinstance(w_cm, model.W_CompiledMethod):
        raise PrimitiveFailedError()
    code = w_cm.primitive()
    if code:
        raise PrimitiveFailedError("withArgs:executeMethod: not support with primitive method")
    return w_cm.create_frame(interp.space, w_rcvr, args_w)


# XXX we might want to disable the assert_class checks in the 4 primitives below

@expose_primitive(SIGNAL, unwrap_spec=[object], clean_stack=False, no_result=True)
def func(interp, s_frame, w_rcvr):
    assert_class(interp, w_rcvr, interp.space.w_Semaphore)
    wrapper.SemaphoreWrapper(interp.space, w_rcvr).signal(s_frame)

@expose_primitive(WAIT, unwrap_spec=[object], clean_stack=False, no_result=True)
def func(interp, s_frame, w_rcvr):
    assert_class(interp, w_rcvr, interp.space.w_Semaphore)
    wrapper.SemaphoreWrapper(interp.space, w_rcvr).wait(s_frame)

@expose_primitive(RESUME, unwrap_spec=[object], no_result=True, clean_stack=False)
def func(interp, s_frame, w_rcvr):
    assert_class(interp, w_rcvr, interp.space.w_Process)
    wrapper.ProcessWrapper(interp.space, w_rcvr).resume(s_frame)

@expose_primitive(SUSPEND, unwrap_spec=[object], no_result=True, clean_stack=False)
def func(interp, s_frame, w_rcvr):
    assert_class(interp, w_rcvr, interp.space.w_Process)
    wrapper.ProcessWrapper(interp.space, w_rcvr).suspend(s_frame)



@expose_primitive(FLUSH_CACHE, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    w_rcvr = assert_pointers(w_rcvr)
    s_class = w_rcvr.as_class_get_shadow(interp.space)
    s_class.flush_method_caches()
    return w_rcvr

# ___________________________________________________________________________
# BlockClosure Primitives

CLOSURE_COPY_WITH_COPIED_VALUES = 200
CLOSURE_VALUE = 201
CLOSURE_VALUE_ = 202
CLOSURE_VALUE_VALUE = 203
CLOSURE_VALUE_VALUE_VALUE = 204
CLOSURE_VALUE_VALUE_VALUE_VALUE = 205
CLOSURE_VALUE_WITH_ARGS = 206 #valueWithArguments:
CLOSURE_VALUE_NO_CONTEXT_SWITCH = 221
CLOSURE_VALUE_NO_CONTEXT_SWITCH_ = 222

@expose_primitive(CLOSURE_COPY_WITH_COPIED_VALUES, unwrap_spec=[object, int, list])
def func(interp, s_frame, outerContext, numArgs, copiedValues):
    w_context = interp.space.newClosure(outerContext, s_frame.pc(),
                                                        numArgs, copiedValues)
    return w_context


def activateClosure(interp, w_block, args_w):
    space = interp.space
    assert_class(interp, w_block, space.w_BlockClosure)
    block = wrapper.BlockClosureWrapper(space, w_block)
    if not block.numArgs() == len(args_w):
        raise PrimitiveFailedError()
    outer_ctxt_class = block.outerContext().getclass(space)
    if not (outer_ctxt_class is space.w_MethodContext
                or outer_ctxt_class is space.w_BlockContext):
        raise PrimitiveFailedError()

    # additionally to the smalltalk implementation, this also pushes
    # args and copiedValues
    s_new_frame = block.create_frame(args_w)
    w_closureMethod = s_new_frame.w_method()

    assert isinstance(w_closureMethod, model.W_CompiledMethod)
    assert w_block is not block.outerContext()

    return s_new_frame


@expose_primitive(CLOSURE_VALUE, unwrap_spec=[object], result_is_new_frame=True)
def func(interp, s_frame, w_block_closure):
    return activateClosure(interp, w_block_closure, [])

@expose_primitive(CLOSURE_VALUE_, unwrap_spec=[object, object], result_is_new_frame=True)
def func(interp, s_frame, w_block_closure, w_a0):
    return activateClosure(interp, w_block_closure, [w_a0])

@expose_primitive(CLOSURE_VALUE_VALUE, unwrap_spec=[object, object, object], result_is_new_frame=True)
def func(interp, s_frame, w_block_closure, w_a0, w_a1):
    return activateClosure(interp, w_block_closure, [w_a0, w_a1])

@expose_primitive(CLOSURE_VALUE_VALUE_VALUE, unwrap_spec=[object, object, object, object], result_is_new_frame=True)
def func(interp, s_frame, w_block_closure, w_a0, w_a1, w_a2):
    return activateClosure(interp, w_block_closure, [w_a0, w_a1, w_a2])

@expose_primitive(CLOSURE_VALUE_VALUE_VALUE_VALUE, unwrap_spec=[object, object, object, object, object], result_is_new_frame=True)
def func(interp, s_frame, w_block_closure, w_a0, w_a1, w_a2, w_a3):
    return activateClosure(interp, w_block_closure, [w_a0, w_a1, w_a2, w_a3])

@expose_primitive(CLOSURE_VALUE_WITH_ARGS, unwrap_spec=[object, list], result_is_new_frame=True)
def func(interp, s_frame, w_block_closure, args_w):
    return activateClosure(interp, w_block_closure, args_w)

@expose_primitive(CLOSURE_VALUE_NO_CONTEXT_SWITCH, unwrap_spec=[object], result_is_new_frame=True, may_context_switch=False)
def func(interp, s_frame, w_block_closure):
    return activateClosure(interp, w_block_closure, [])

@expose_primitive(CLOSURE_VALUE_NO_CONTEXT_SWITCH_, unwrap_spec=[object, object], result_is_new_frame=True, may_context_switch=False)
def func(interp, s_frame, w_block_closure, w_a0):
    return activateClosure(interp, w_block_closure, [w_a0])

# ___________________________________________________________________________
# Override the default primitive to give latitude to the VM in context management.

CTXT_AT = 210
CTXT_AT_PUT = 211
CTXT_SIZE = 212

prim_table[CTXT_AT] = prim_table[AT]
prim_table[CTXT_AT_PUT] = prim_table[AT_PUT]
prim_table[CTXT_SIZE] = prim_table[SIZE]
# ___________________________________________________________________________
# Drawing

IDLE_FOR_MICROSECONDS = 230
FORCE_DISPLAY_UPDATE = 231

@expose_primitive(IDLE_FOR_MICROSECONDS, unwrap_spec=[object, int], no_result=True, clean_stack=False)
def func(interp, s_frame, w_rcvr, time_mu_s):
    import time
    s_frame.pop()
    time_s = time_mu_s / 1000000.0
    interp.interrupt_check_counter = 0
    interp.quick_check_for_interrupt(s_frame, dec=0)
    time.sleep(time_s)
    interp.interrupt_check_counter = 0
    interp.quick_check_for_interrupt(s_frame, dec=0)

@expose_primitive(FORCE_DISPLAY_UPDATE, unwrap_spec=[object])
def func(interp, s_frame, w_rcvr):
    interp.space.display().flip(force=True)
    return w_rcvr

# ___________________________________________________________________________
# VM implementor primitives
VM_CLEAR_PROFILE = 250
VM_CONTROL_PROFILING = 251
VM_PROFILE_SAMPLES_INTO = 252
VM_PROFILE_INFO_INTO = 253
VM_PARAMETERS = 254
INST_VARS_PUT_FROM_STACK = 255 # Never used except in Disney tests.  Remove after 2.3 release.

@expose_primitive(VM_PARAMETERS)
def func(interp, s_frame, argcount):
    """Behaviour depends on argument count:
            0 args: return an Array of VM parameter values;
            1 arg:  return the indicated VM parameter;
            2 args: set the VM indicated parameter.
        VM parameters are numbered as follows:
            1   end of old-space (0-based, read-only)
            2   end of young-space (read-only)
            3   end of memory (read-only)
            4   allocationCount (read-only)
            5   allocations between GCs (read-write)
            6   survivor count tenuring threshold (read-write)
            7   full GCs since startup (read-only)
            8   total milliseconds in full GCs since startup (read-only)
            9   incremental GCs since startup (read-only)
            10  total milliseconds in incremental GCs since startup (read-only)
            11  tenures of surving objects since startup (read-only)
            12-20 specific to the translating VM
            21  root table size (read-only)
            22  root table overflows since startup (read-only)
            23  bytes of extra memory to reserve for VM buffers, plugins, etc.
            24  memory threshold above which shrinking object memory (rw)
            25  memory headroom when growing object memory (rw)
            26  interruptChecksEveryNms - force an ioProcessEvents every N milliseconds, in case the image  is not calling getNextEvent often (rw)
            27  number of times mark loop iterated for current IGC/FGC (read-only) includes ALL marking
            28  number of times sweep loop iterated  for current IGC/FGC (read-only)
            29  number of times make forward loop iterated for current IGC/FGC (read-only)
            30  number of times compact move loop iterated for current IGC/FGC (read-only)
            31  number of grow memory requests (read-only)
            32  number of shrink memory requests (read-only)
            33  number of root table entries used for current IGC/FGC (read-only)
            34  number of allocations done before current IGC/FGC (read-only)
            35  number of survivor objects after current IGC/FGC (read-only)
            36  millisecond clock when current IGC/FGC completed (read-only)
            37  number of marked objects for Roots of the world, not including Root Table entries for current IGC/FGC (read-only)
            38  milliseconds taken by current IGC  (read-only)
            39  Number of finalization signals for Weak Objects pending when current IGC/FGC completed (read-only)
            40  BytesPerWord for this image
            41  imageFormatVersion for the VM
            42  nil (number of stack pages in use in Stack VM)
            43  nil (desired number of stack pages in Stack VM)
            44  nil (size of eden, in bytes in Stack VM)
            45  nil (desired size of eden in Stack VM)
            46-55 nil; reserved for VM parameters that persist in the image (such as eden above)
            56  number of process switches since startup (read-only)
            57  number of ioProcessEvents calls since startup (read-only)
            58  number of ForceInterruptCheck calls since startup (read-only)
            59  number of check event calls since startup (read-only)

        Note: Thanks to Ian Piumarta for this primitive."""
    if not 0 <= argcount <= 2:
        raise PrimitiveFailedError

    s_frame.pop() # receiver
    if argcount == 0:
        return interp.space.wrap_list([interp.space.wrap_int(0)]*59)
    s_frame.pop() # index (really the receiver, index has been removed above)
    if argcount == 1:
        return interp.space.wrap_int(0)
    s_frame.pop() # new value
    if argcount == 2:
        # return the 'old value'
        return interp.space.wrap_int(0)

# ___________________________________________________________________________
# PrimitiveLoadInstVar
#
# These are some wacky bytecodes in squeak.  They are defined to do
# the following:
#   primitiveLoadInstVar
#     | thisReceiver |
#     thisReceiver := self popStack.
#     self push: (self fetchPointer: primitiveIndex-264 ofObject: thisReceiver)

for i in range(264, 520):
    def make_prim(i):
        @expose_primitive(i, unwrap_spec=[object])
        def func(interp, s_frame, w_object):
            return w_object.fetch(interp.space, i - 264)
    globals()["INST_VAR_AT_%d" % (i-264)] = i
    make_prim(i)

unrolling_prim_table = unroll.unrolling_iterable(prim_table_implemented_only)
