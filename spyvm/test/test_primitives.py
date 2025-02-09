import py, os, math, time
from spyvm import model, model_display, storage_contexts, constants, primitives, wrapper, display
from spyvm.primitives import prim_table, PrimitiveFailedError
from spyvm.plugins import bitblt
from rpython.rlib.rfloat import isinf, isnan
from rpython.rlib.rarithmetic import intmask
from rpython.rtyper.lltypesystem import lltype, rffi
from .util import create_space, copy_to_module, cleanup_module, TestInterpreter, very_slow_test

def setup_module():
    space = create_space(bootstrap = True)
    wrap = space.w
    bootstrap_class = space.bootstrap_class
    new_frame = space.make_frame
    copy_to_module(locals(), __name__)

def teardown_module():
    cleanup_module(__name__)

class MockFrame(model.W_PointersObject):
    def __init__(self, space, stack):
        size = 6 + len(stack) + 6
        self.initialize_storage(space, size)
        self.store_all(space, [None] * 6 + stack + [space.w_nil] * 6)
        s_self = self.as_blockcontext_get_shadow(space)
        s_self.init_stack_and_temps()
        s_self.reset_stack()
        s_self.push_all(stack)
        s_self.store_expected_argument_count(0)
        self.w_class = space.w_MethodContext

    def as_blockcontext_get_shadow(self, space):
        if not isinstance(self.shadow, storage_contexts.ContextPartShadow):
            self.shadow = storage_contexts.ContextPartShadow(space, self, self.size(), is_block_context=True)
        return self.shadow

IMAGENAME = "anImage.image"

def mock(space, stack, context = None):
    mapped_stack = [space.w(x) for x in stack]
    if context is None:
        frame = MockFrame(space, mapped_stack)
    else:
        frame = context
        for i in range(len(stack)):
            frame.as_context_get_shadow(space).push(stack[i])
    interp = TestInterpreter(space)
    interp.space._image_name.set(IMAGENAME)
    return interp, frame, len(stack)

def _prim(space, code, stack, context = None):
    interp, w_frame, argument_count = mock(space, stack, context)
    prim_table[code](interp, w_frame.as_context_get_shadow(space), argument_count-1)
    res = w_frame.as_context_get_shadow(space).pop()
    s_frame = w_frame.as_context_get_shadow(space)
    assert not s_frame.stackdepth() - s_frame.tempsize() # check args are consumed
    return res

def prim(code, stack, context = None):
    return _prim(space, code, stack, context)

def prim_fails(code, stack):
    interp, w_frame, argument_count = mock(space, stack)
    orig_stack = list(w_frame.as_context_get_shadow(space).stack())
    with py.test.raises(PrimitiveFailedError):
        prim_table[code](interp, w_frame.as_context_get_shadow(space), argument_count - 1)
    assert w_frame.as_context_get_shadow(space).stack() == orig_stack

# smallinteger tests
def test_small_int_add():
    assert prim(primitives.ADD, [1,2]).value == 3
    assert prim(primitives.ADD, [3,4]).value == 7

def test_small_int_add_fail():
    w_result = prim_fails(primitives.ADD, [constants.MAXINT, 2])
    # assert isinstance(w_result, model.W_LargePositiveInteger1Word)
    # assert w_result.value == constants.TAGGED_MAXINT + 2
    # prim_fails(primitives.ADD, [constants.TAGGED_MAXINT, constants.TAGGED_MAXINT * 2])

def test_small_int_minus():
    assert prim(primitives.SUBTRACT, [5,9]).value == -4

def test_small_int_minus_fail():
    prim_fails(primitives.SUBTRACT, [constants.MININT,1])
    prim_fails(primitives.SUBTRACT,
               [constants.MININT, constants.MAXINT])

def test_small_int_multiply():
    assert prim(primitives.MULTIPLY, [6,3]).value == 18

def test_small_int_multiply_overflow():
    w_result = prim_fails(primitives.MULTIPLY, [constants.MAXINT, 2])
    #assert isinstance(w_result, model.W_LargePositiveInteger1Word)
    #assert w_result.value == constants.TAGGED_MAXINT * 2
    prim_fails(primitives.MULTIPLY, [constants.MAXINT, constants.MAXINT])
    prim_fails(primitives.MULTIPLY, [constants.MAXINT, -4])
    prim_fails(primitives.MULTIPLY, [constants.MININT, constants.MAXINT])
    prim_fails(primitives.MULTIPLY, [constants.MININT, 2])

def test_small_int_divide():
    assert prim(primitives.DIVIDE, [6,3]).value == 2

def test_small_int_divide_fail():
    prim_fails(primitives.DIVIDE, [12, 0])
    prim_fails(primitives.DIVIDE, [12, 7])

def test_small_int_mod():
    assert prim(primitives.MOD, [12,7]).value == 5

def test_small_int_mod_fail():
    prim_fails(primitives.MOD, [12, 0])

def test_small_int_div():
    assert prim(primitives.DIV, [12,3]).value == 4
    assert prim(primitives.DIV, [12,7]).value == 1

def test_small_int_div_fail():
    prim_fails(primitives.DIV, [12, 0])

def test_small_int_quo():
    assert prim(primitives.QUO, [12,3]).value == 4
    assert prim(primitives.QUO, [12,7]).value == 1
    assert prim(primitives.QUO, [-9,4]).value == -2
    assert prim(primitives.QUO, [-12,12]).value == -1
    assert prim(primitives.QUO, [-12,11]).value == -1
    assert prim(primitives.QUO, [-12,13]).value == 0
    assert prim(primitives.QUO, [-12,-12]).value == 1
    assert prim(primitives.QUO, [12,-11]).value == -1
    assert prim(primitives.QUO, [12,-13]).value == 0

def test_small_int_quo_fail():
    prim_fails(primitives.QUO, [12, 0])

def test_small_int_bit_and():
    assert prim(primitives.BIT_AND, [2, 4]).value == 0
    assert prim(primitives.BIT_AND, [2, 3]).value == 2
    assert prim(primitives.BIT_AND, [3, 4]).value == 0
    assert prim(primitives.BIT_AND, [4, 4]).value == 4

def test_small_int_bit_or():
    assert prim(primitives.BIT_OR, [2, 4]).value == 6
    assert prim(primitives.BIT_OR, [2, 3]).value == 3
    assert prim(primitives.BIT_OR, [3, 4]).value == 7
    assert prim(primitives.BIT_OR, [4, 4]).value == 4

def test_small_int_bit_xor():
    assert prim(primitives.BIT_XOR, [2, 4]).value == 6
    assert prim(primitives.BIT_XOR, [2, 3]).value == 1
    assert prim(primitives.BIT_XOR, [3, 4]).value == 7
    assert prim(primitives.BIT_XOR, [4, 4]).value == 0

def test_small_int_bit_shift():
    assert prim(primitives.BIT_SHIFT, [0, -3]).value == 0
    assert prim(primitives.BIT_SHIFT, [0, -2]).value == 0
    assert prim(primitives.BIT_SHIFT, [0, -1]).value == 0
    assert prim(primitives.BIT_SHIFT, [0, 0]).value == 0
    assert prim(primitives.BIT_SHIFT, [0, 1]).value == 0
    assert prim(primitives.BIT_SHIFT, [0, 2]).value == 0
    assert prim(primitives.BIT_SHIFT, [0, 3]).value == 0

def test_small_int_bit_shift_positive():
    assert prim(primitives.BIT_SHIFT, [4, -3]).value == 0
    assert prim(primitives.BIT_SHIFT, [4, -2]).value == 1
    assert prim(primitives.BIT_SHIFT, [4, -1]).value == 2
    assert prim(primitives.BIT_SHIFT, [4, 0]).value == 4
    assert prim(primitives.BIT_SHIFT, [4, 1]).value == 8
    assert prim(primitives.BIT_SHIFT, [4, 2]).value == 16
    assert prim(primitives.BIT_SHIFT, [4, 3]).value == 32
    assert prim(primitives.BIT_SHIFT, [4, 27]).value == 536870912

def test_small_int_bit_shift_negative():
    assert prim(primitives.BIT_SHIFT, [-4, -3]).value == -1
    assert prim(primitives.BIT_SHIFT, [-4, -2]).value == -1
    assert prim(primitives.BIT_SHIFT, [-4, -1]).value == -2
    assert prim(primitives.BIT_SHIFT, [-4, 0]).value == -4
    assert prim(primitives.BIT_SHIFT, [-4, 1]).value == -8
    assert prim(primitives.BIT_SHIFT, [-4, 2]).value == -16
    assert prim(primitives.BIT_SHIFT, [-4, 3]).value == -32
    assert prim(primitives.BIT_SHIFT, [-4, 27]).value == -536870912

def test_small_int_bit_shift_fail():
    prim_fails(primitives.BIT_SHIFT, [4, 32])
    prim_fails(primitives.BIT_SHIFT, [4, 31])
    w_result = prim(primitives.BIT_SHIFT, [4, 29])
    assert isinstance(w_result, model.W_LargePositiveInteger1Word)
    assert w_result.value == intmask(4 << 29)

def test_smallint_as_float():
    assert prim(primitives.SMALLINT_AS_FLOAT, [12]).value == 12.0

def test_float_add():
    assert prim(primitives.FLOAT_ADD, [1.0,2.0]).value == 3.0
    assert prim(primitives.FLOAT_ADD, [3.0,4.5]).value == 7.5

def test_float_subtract():
    assert prim(primitives.FLOAT_SUBTRACT, [1.0,2.0]).value == -1.0
    assert prim(primitives.FLOAT_SUBTRACT, [15.0,4.5]).value == 10.5

def test_float_multiply():
    assert prim(primitives.FLOAT_MULTIPLY, [10.0,2.0]).value == 20.0
    assert prim(primitives.FLOAT_MULTIPLY, [3.0,4.5]).value == 13.5

def test_float_divide():
    assert prim(primitives.FLOAT_DIVIDE, [1.0,2.0]).value == 0.5
    assert prim(primitives.FLOAT_DIVIDE, [3.5,4.0]).value == 0.875

def test_float_truncate():
    assert prim(primitives.FLOAT_TRUNCATED, [-4.6]).value == -4
    assert prim(primitives.FLOAT_TRUNCATED, [-4.5]).value == -4
    assert prim(primitives.FLOAT_TRUNCATED, [-4.4]).value == -4
    assert prim(primitives.FLOAT_TRUNCATED, [4.4]).value == 4
    assert prim(primitives.FLOAT_TRUNCATED, [4.5]).value == 4
    assert prim(primitives.FLOAT_TRUNCATED, [4.6]).value == 4

def test_float_times_two_power():
    assert prim(primitives.FLOAT_TIMES_TWO_POWER, [2.0, 10]).value == 2.0 ** 11
    assert prim(primitives.FLOAT_TIMES_TWO_POWER, [-213.0, 1020]).value == float('-inf')
    assert prim(primitives.FLOAT_TIMES_TWO_POWER, [213.0, 1020]).value == float('inf')

def test_at():
    w_obj = bootstrap_class(0, varsized=True).as_class_get_shadow(space).new(1)
    foo = wrap("foo")
    w_obj.store(space, 0, foo)
    assert prim(primitives.AT, [w_obj, 1]) is foo

    w_obj = model.W_Float(1.1)
    foo = wrap(1)
    w_obj.store(space, 0, foo)
    assert prim(primitives.AT, [w_obj, 1]) == foo

def test_invalid_at():
    w_obj = bootstrap_class(0).as_class_get_shadow(space).new()
    prim_fails(primitives.AT, [w_obj, 1])

def test_at_put():
    w_obj = bootstrap_class(0, varsized=1).as_class_get_shadow(space).new(1)
    assert prim(primitives.AT_PUT, [w_obj, 1, 22]).value == 22
    assert prim(primitives.AT, [w_obj, 1]).value == 22

def test_at_and_at_put_bytes():
    w_str = wrap("abc")
    prim_fails(primitives.AT_PUT, [w_str, 1, "d"])
    assert prim(primitives.AT_PUT, [w_str, 1, ord('d')]).value == ord('d')
    assert prim(primitives.AT, [w_str, 1]).value == ord('d')
    assert prim(primitives.AT, [w_str, 2]).value == ord('b')
    assert prim(primitives.AT, [w_str, 3]).value == ord('c')

def test_invalid_at_put():
    w_obj = bootstrap_class(0).as_class_get_shadow(space).new()
    prim_fails(primitives.AT_PUT, [w_obj, 1, 22])

def test_size():
    w_obj = bootstrap_class(0, varsized=True).as_class_get_shadow(space).new(0)
    assert prim(primitives.SIZE, [w_obj]).value == 0
    w_obj = bootstrap_class(3, varsized=True).as_class_get_shadow(space).new(5)
    assert prim(primitives.SIZE, [w_obj]).value == 5

def test_size_of_compiled_method():
    literalsize = 3
    bytecount = 3
    w_cm = model.W_CompiledMethod(space, bytecount)
    w_cm.literalsize = literalsize
    assert prim(primitives.SIZE, [w_cm]).value == (literalsize+1)*constants.BYTES_PER_WORD + bytecount

def test_string_at():
    assert prim(primitives.STRING_AT, ["foobar", 4]) == wrap("b")

def test_string_at_put():
    test_str = wrap("foobar")
    assert prim(primitives.STRING_AT_PUT, [test_str, 4, "c"]) == wrap("c")
    exp = "foocar"
    for i in range(len(exp)):
        assert prim(primitives.STRING_AT, [test_str, i]) == wrap(exp[i])

def test_invalid_object_at():
    prim_fails(primitives.OBJECT_AT, ["q", constants.CHARACTER_VALUE_INDEX+2])

def test_invalid_object_at_put():
    w_obj = bootstrap_class(1).as_class_get_shadow(space).new()
    prim_fails(primitives.OBJECT_AT_PUT, [w_obj, 2, 42])

def test_string_at_put():
    test_str = wrap("foobar")
    assert prim(primitives.STRING_AT_PUT, [test_str, 4, "c"]) == wrap("c")
    exp = "foocar"
    for i in range(1,len(exp)+1):
        assert prim(primitives.STRING_AT, [test_str, i]) == wrap(exp[i-1])

def test_new():
    w_Object = space.classtable['w_Object']
    w_res = prim(primitives.NEW, [w_Object])
    assert w_res.getclass(space).is_same_object(w_Object)

def test_invalid_new():
    prim_fails(primitives.NEW, [space.w_String])

def test_new_with_arg():
    w_res = prim(primitives.NEW_WITH_ARG, [space.w_String, 20])
    assert w_res.getclass(space).is_same_object(space.w_String)
    assert w_res.size() == 20

def test_new_with_arg_for_non_variable_sized():
    prim_fails(primitives.NEW_WITH_ARG, [space.classtable['w_ArrayedCollection'], 10])

def test_new_with_arg_for_non_variable_sized0():
    w_res = prim(primitives.NEW_WITH_ARG, [space.classtable['w_ArrayedCollection'], 0])
    assert w_res.getclass(space).is_same_object(space.classtable['w_ArrayedCollection'])
    assert w_res.size() == 0

def test_invalid_new_with_arg():
    w_Object = space.classtable['w_Object']
    prim_fails(primitives.NEW_WITH_ARG, [w_Object, 20])

def test_inst_var_at():
    # n.b.: 1-based indexing!
    w_v = prim(primitives.INST_VAR_AT,
               ["q", constants.CHARACTER_VALUE_INDEX+1])
    assert w_v.value == ord("q")

def test_inst_var_at_invalid():
    # n.b.: 1-based indexing! (and an invalid index)
    prim_fails(primitives.INST_VAR_AT, ["q", constants.CHARACTER_VALUE_INDEX+2])

def test_inst_var_at_put():
    # n.b.: 1-based indexing!
    w_q = space.w_Character.as_class_get_shadow(space).new()
    vidx = constants.CHARACTER_VALUE_INDEX+1
    ordq = ord("q")
    assert prim(primitives.INST_VAR_AT, [w_q, vidx]).is_nil(space)
    assert prim(primitives.INST_VAR_AT_PUT, [w_q, vidx, ordq]).value == ordq
    assert prim(primitives.INST_VAR_AT, [w_q, vidx]).value == ordq

def test_inst_var_at_put_invalid():
    # n.b.: 1-based indexing! (and an invalid index)
    prim_fails(primitives.INST_VAR_AT_PUT,
               ["q", constants.CHARACTER_VALUE_INDEX+2, "t"])

def test_class():
    assert prim(primitives.CLASS, ["string"]).is_same_object(space.w_String)
    assert prim(primitives.CLASS, [1]).is_same_object(space.w_SmallInteger)

def test_as_oop():
    # I checked potato, and that returns the hash for as_oop
    w_obj = bootstrap_class(0).as_class_get_shadow(space).new()
    w_obj.hash = 22
    assert prim(primitives.AS_OOP, [w_obj]).value == 22

def test_as_oop_not_applicable_to_int():
    prim_fails(primitives.AS_OOP, [22])

def test_const_primitives():
    for (code, const) in [
        (primitives.PUSH_TRUE, space.w_true),
        (primitives.PUSH_FALSE, space.w_false),
        (primitives.PUSH_NIL, space.w_nil),
        (primitives.PUSH_MINUS_ONE, space.w_minus_one),
        (primitives.PUSH_ZERO, space.w_zero),
        (primitives.PUSH_ONE, space.w_one),
        (primitives.PUSH_TWO, space.w_two),
        ]:
        assert prim(code, [space.w_nil]).is_same_object(const)
    assert prim(primitives.PUSH_SELF, [space.w_nil]).is_nil(space)
    assert prim(primitives.PUSH_SELF, ["a"]) is wrap("a")

def test_boolean():
    assert prim(primitives.LESSTHAN, [1,2]).is_same_object(space.w_true)
    assert prim(primitives.GREATERTHAN, [3,4]).is_same_object(space.w_false)
    assert prim(primitives.LESSOREQUAL, [1,2]).is_same_object(space.w_true)
    assert prim(primitives.GREATEROREQUAL, [3,4]).is_same_object(space.w_false)
    assert prim(primitives.EQUAL, [2,2]).is_same_object(space.w_true)
    assert prim(primitives.NOTEQUAL, [2,2]).is_same_object(space.w_false)

def test_float_boolean():
    assert prim(primitives.FLOAT_LESSTHAN, [1.0,2.0]).is_same_object(space.w_true)
    assert prim(primitives.FLOAT_GREATERTHAN, [3.0,4.0]).is_same_object(space.w_false)
    assert prim(primitives.FLOAT_LESSOREQUAL, [1.3,2.6]).is_same_object(space.w_true)
    assert prim(primitives.FLOAT_GREATEROREQUAL, [3.5,4.9]).is_same_object(space.w_false)
    assert prim(primitives.FLOAT_EQUAL, [2.2,2.2]).is_same_object(space.w_true)
    assert prim(primitives.FLOAT_NOTEQUAL, [2.2,2.2]).is_same_object(space.w_false)

def test_block_copy_and_value():
    # see test_interpreter for tests of these opcodes
    return

ROUNDING_DIGITS = 8

def float_equals(w_f,f):
    return round(w_f.value,ROUNDING_DIGITS) == round(f,ROUNDING_DIGITS)

def test_primitive_square_root():
    assert prim(primitives.FLOAT_SQUARE_ROOT, [4.0]).value == 2.0
    assert float_equals(prim(primitives.FLOAT_SQUARE_ROOT, [2.0]), math.sqrt(2))
    prim_fails(primitives.FLOAT_SQUARE_ROOT, [-2.0])

def test_primitive_sin():
    assert prim(primitives.FLOAT_SIN, [0.0]).value == 0.0
    assert float_equals(prim(primitives.FLOAT_SIN, [math.pi]), 0.0)
    assert float_equals(prim(primitives.FLOAT_SIN, [math.pi/2]), 1.0)

def test_primitive_arctan():
    assert prim(primitives.FLOAT_ARCTAN, [0.0]).value == 0.0
    assert float_equals(prim(primitives.FLOAT_ARCTAN, [1]), math.pi/4)
    assert float_equals(prim(primitives.FLOAT_ARCTAN, [1e99]), math.pi/2)

def test_primitive_log_n():
    assert prim(primitives.FLOAT_LOG_N, [1.0]).value == 0.0
    assert prim(primitives.FLOAT_LOG_N, [math.e]).value == 1.0
    assert float_equals(prim(primitives.FLOAT_LOG_N, [10.0]), math.log(10))
    assert isinf(prim(primitives.FLOAT_LOG_N, [0.0]).value) # works also for negative infinity
    assert isnan(prim(primitives.FLOAT_LOG_N, [-1.0]).value)

def test_primitive_exp():
    assert float_equals(prim(primitives.FLOAT_EXP, [-1.0]), 1/math.e)
    assert prim(primitives.FLOAT_EXP, [0]).value == 1
    assert float_equals(prim(primitives.FLOAT_EXP, [1]), math.e)
    assert float_equals(prim(primitives.FLOAT_EXP, [math.log(10)]), 10)

def equals_ttp(rcvr,arg,res):
    return float_equals(prim(primitives.FLOAT_TIMES_TWO_POWER, [rcvr,arg]), res)

def test_times_two_power():
    assert equals_ttp(1,1,2)
    assert equals_ttp(1.5,1,3)
    assert equals_ttp(2,4,32)
    assert equals_ttp(0,2,0)
    assert equals_ttp(-1,2,-4)
    assert equals_ttp(1.5,0,1.5)
    assert equals_ttp(1.5,-1,0.75)

def test_primitive_milliseconds_clock():
    start = prim(primitives.MILLISECOND_CLOCK, [0]).value
    time.sleep(0.3)
    stop = prim(primitives.MILLISECOND_CLOCK, [0]).value
    assert start + 250 <= stop

def test_signal_at_milliseconds():
    future = prim(primitives.MILLISECOND_CLOCK, [0]).value + 400
    sema = space.w_Semaphore.as_class_get_shadow(space).new()
    prim(primitives.SIGNAL_AT_MILLISECONDS, [space.w_nil, sema, future])
    assert space.objtable["w_timerSemaphore"] is sema

def test_inc_gc():
    # Should not fail :-)
    prim(primitives.INC_GC, [42]) # Dummy arg

def test_full_gc():
    # Should not fail :-)
    prim(primitives.FULL_GC, [42]) # Dummy arg

def test_interrupt_semaphore():
    prim(primitives.INTERRUPT_SEMAPHORE, [1, space.w_true])
    assert space.objtable["w_interrupt_semaphore"].is_nil(space)

    class SemaphoreInst(model.W_Object):
        def getclass(self, space):
            return space.w_Semaphore
    w_semaphore = SemaphoreInst()
    prim(primitives.INTERRUPT_SEMAPHORE, [1, w_semaphore])
    assert space.objtable["w_interrupt_semaphore"] is w_semaphore

def test_seconds_clock():
    now = int(time.time())
    w_smalltalk_now1 = prim(primitives.SECONDS_CLOCK, [42])
    w_smalltalk_now2 = prim(primitives.SECONDS_CLOCK, [42])
    # the test now is flaky, because we assume both have the same type
    if isinstance(w_smalltalk_now1, model.W_BytesObject):
        assert (now % 256 - ord(w_smalltalk_now1.bytes[0])) % 256 <= 2
        # the high-order byte should only change by one (and even that is
        # extreeemely unlikely)
        assert (ord(w_smalltalk_now2.bytes[-1]) - ord(w_smalltalk_now1.bytes[-1])) <= 1
    else:
        assert w_smalltalk_now2.value - w_smalltalk_now1.value <= 1

def test_load_inst_var():
    " try to test the LoadInstVar primitives a little "
    w_v = prim(primitives.INST_VAR_AT_0, ["q"])
    assert w_v.value == ord("q")

def test_new_method():
    bytecode = ''.join(map(chr, [ 16, 119, 178, 154, 118, 164, 11, 112, 16, 118, 177, 224, 112, 16, 119, 177, 224, 176, 124 ]))

    shadow = bootstrap_class(0).as_class_get_shadow(space)
    w_method = prim(primitives.NEW_METHOD, [space.w_CompiledMethod, len(bytecode), 1025])
    assert w_method.literalat0(space, 0).value == 1025
    assert w_method.literalsize == 2
    assert w_method.literalat0(space, 1).is_nil(space)
    assert w_method.bytes == ["\x00"] * len(bytecode)

def test_image_name():
    w_v = prim(primitives.IMAGE_NAME, [2])
    assert w_v.bytes == list(IMAGENAME)

def test_clone():
    w_obj = bootstrap_class(1, varsized=True).as_class_get_shadow(space).new(1)
    w_obj.atput0(space, 0, space.wrap_int(1))
    w_v = prim(primitives.CLONE, [w_obj])
    assert space.unwrap_int(w_v.at0(space, 0)) == 1
    w_obj.atput0(space, 0, space.wrap_int(2))
    assert space.unwrap_int(w_v.at0(space, 0)) == 1

def test_file_open_write(monkeypatch):
    def open_write(filename, mode, perm):
        assert filename == "nonexistant"
        assert mode == os.O_RDWR | os.O_CREAT | os.O_TRUNC
        return 42
    monkeypatch.setattr(os, "open", open_write)
    try:
        w_c = prim(primitives.FILE_OPEN, [1, space.wrap_string("nonexistant"), space.w_true])
    finally:
        monkeypatch.undo()
    assert space.unwrap_int(w_c) == 42

def test_file_open_read(monkeypatch):
    def open_read(filename, mode, perm):
        assert filename == "file"
        assert mode == os.O_RDONLY
        return 42
    monkeypatch.setattr(os, "open", open_read)
    try:
        w_c = prim(primitives.FILE_OPEN, [1, space.wrap_string("file"), space.w_false])
    finally:
        monkeypatch.undo()
    assert space.unwrap_int(w_c) == 42

def test_file_close(monkeypatch):
    def close(fd):
        assert fd == 42
    monkeypatch.setattr(os, "close", close)
    try:
        w_c = prim(primitives.FILE_CLOSE, [1, space.wrap_int(42)])
    finally:
        monkeypatch.undo()

def test_file_write(monkeypatch):
    def write(fd, string):
        assert fd == 42
        assert string == "ell"
    monkeypatch.setattr(os, "write", write)
    try:
        w_c = prim(
            primitives.FILE_WRITE,
            [1, space.wrap_int(42), space.wrap_string("hello"), space.wrap_int(2), space.wrap_int(3)]
        )
    finally:
        monkeypatch.undo()

def test_file_write_errors(monkeypatch):
    with py.test.raises(PrimitiveFailedError):
        w_c = prim(
            primitives.FILE_WRITE,
            [1, space.wrap_int(42), space.wrap_string("hello"), space.wrap_int(-1), space.wrap_int(3)]
        )
    with py.test.raises(PrimitiveFailedError):
        w_c = prim(
            primitives.FILE_WRITE,
            [1, space.wrap_int(42), space.wrap_string("hello"), space.wrap_int(2), space.wrap_int(-1)]
        )

def test_directory_delimitor():
    w_c = prim(primitives.DIRECTORY_DELIMITOR, [1])
    assert space.unwrap_char(w_c) == os.path.sep

def test_primitive_closure_copyClosure():
    w_frame, s_frame = new_frame("<never called, but used for method generation>")
    w_outer_frame, s_initial_context = new_frame("<never called, but used for method generation>")
    w_block = prim(primitives.CLOSURE_COPY_WITH_COPIED_VALUES, map(wrap,
                    [w_outer_frame, 2, [wrap(1), wrap(2)]]), w_frame)
    assert not w_block.is_nil(space)
    w_w_block = wrapper.BlockClosureWrapper(space, w_block)
    assert w_w_block.startpc() is 5
    assert w_w_block.at0(0) == wrap(1)
    assert w_w_block.at0(1) == wrap(2)
    assert w_w_block.numArgs() is 2

def test_primitive_string_copy():
    w_r = prim(primitives.STRING_REPLACE, ["aaaaa", 1, 5, "ababab", 1])
    assert w_r.as_string() == "ababa"
    w_r = prim(primitives.STRING_REPLACE, ["aaaaa", 1, 5, "ababab", 2])
    assert w_r.as_string() == "babab"
    w_r = prim(primitives.STRING_REPLACE, ["aaaaa", 2, 5, "ccccc", 1])
    assert w_r.as_string() == "acccc"
    w_r = prim(primitives.STRING_REPLACE, ["aaaaa", 2, 4, "ccccc", 1])
    assert w_r.as_string() == "accca"
    prim_fails(primitives.STRING_REPLACE, ["aaaaa", 0, 4, "ccccc", 1])
    prim_fails(primitives.STRING_REPLACE, ["aaaaa", 1, 6, "ccccc", 2])
    prim_fails(primitives.STRING_REPLACE, ["aaaaa", 2, 6, "ccccc", 1])
    prim_fails(primitives.STRING_REPLACE, [['a', 'b'], 1, 4, "ccccc", 1])

def build_up_closure_environment(args, copiedValues=[]):
    w_frame, s_initial_context = new_frame("<never called, but used for method generation>")

    size_arguments = len(args)
    closure = space.newClosure(w_frame, 4, #pc
                                size_arguments, copiedValues)
    s_initial_context.push_all([closure] + args)
    interp = TestInterpreter(space)
    s_active_context = prim_table[primitives.CLOSURE_VALUE + size_arguments](interp, s_initial_context, size_arguments)
    return s_initial_context, closure, s_active_context

def test_primitive_closure_value():
    s_initial_context, closure, s_new_context = build_up_closure_environment([])

    assert s_new_context.closure._w_self is closure
    assert s_new_context.s_sender() is s_initial_context
    assert s_new_context.w_receiver().is_nil(space)

def test_primitive_closure_value_value():
    s_initial_context, closure, s_new_context = build_up_closure_environment([
            wrap("first arg"), wrap("second arg")])

    assert s_new_context.closure._w_self is closure
    assert s_new_context.s_sender() is s_initial_context
    assert s_new_context.w_receiver().is_nil(space)
    assert s_new_context.gettemp(0).as_string() == "first arg"
    assert s_new_context.gettemp(1).as_string() == "second arg"

def test_primitive_closure_value_value_with_temps():
    s_initial_context, closure, s_new_context = build_up_closure_environment(
            [wrap("first arg"), wrap("second arg")],
        copiedValues=[wrap('some value')])

    assert s_new_context.closure._w_self is closure
    assert s_new_context.s_sender() is s_initial_context
    assert s_new_context.w_receiver().is_nil(space)
    assert s_new_context.gettemp(0).as_string() == "first arg"
    assert s_new_context.gettemp(1).as_string() == "second arg"
    assert s_new_context.gettemp(2).as_string() == "some value"

@very_slow_test
def test_primitive_some_instance():
    import gc; gc.collect()
    someInstance = map(space.wrap_list, [[1], [2]])
    w_r = prim(primitives.SOME_INSTANCE, [space.w_Array])
    assert w_r.getclass(space) is space.w_Array

@very_slow_test
def test_primitive_next_instance():
    someInstances = map(space.wrap_list, [[2], [3]])
    w_frame, s_context = new_frame("<never called, but needed for method generation>")

    s_context.push(space.w_Array)
    interp = TestInterpreter(space)
    prim_table[primitives.SOME_INSTANCE](interp, s_context, 0)
    w_1 = s_context.pop()
    assert w_1.getclass(space) is space.w_Array

    s_context.push(w_1)
    prim_table[primitives.NEXT_INSTANCE](interp, s_context, 0)
    w_2 = s_context.pop()
    assert w_2.getclass(space) is space.w_Array
    assert w_1 is not w_2

@very_slow_test
def test_primitive_next_instance_wo_some_instance_in_same_frame():
    someInstances = map(space.wrap_list, [[2], [3]])
    w_frame, s_context = new_frame("<never called, but needed for method generation>")

    s_context.push(space.w_Array)
    interp = TestInterpreter(space)
    w_1 = someInstances[0]
    assert w_1.getclass(space) is space.w_Array

    s_context.push(w_1)
    prim_table[primitives.NEXT_INSTANCE](interp, s_context, 0)
    w_2 = s_context.pop()
    assert w_2.getclass(space) is space.w_Array
    assert w_1 is not w_2

def test_primitive_value_no_context_switch(monkeypatch):
    class Context_switched(Exception):
        pass
    class Stepping(Exception):
        pass

    def quick_check_for_interrupt(s_frame, dec=1):
        raise Context_switched
    def step(s_frame):
        raise Stepping

    w_frame, s_initial_context = new_frame("<never called, but used for method generation>")

    closure = space.newClosure(w_frame, 4, 0, [])
    s_frame = w_frame.as_methodcontext_get_shadow(space)
    interp = TestInterpreter(space)
    interp._loop = True

    try:
        monkeypatch.setattr(interp, "quick_check_for_interrupt", quick_check_for_interrupt)
        monkeypatch.setattr(interp, "step", step)
        try:
            s_frame.push(closure)
            prim_table[primitives.CLOSURE_VALUE](interp, s_frame, 0)
        except Context_switched:
            assert True
        except Stepping:
            assert False
        try:
            s_frame.push(closure)
            prim_table[primitives.CLOSURE_VALUE_NO_CONTEXT_SWITCH](interp, s_frame, 0)
        except Context_switched:
            assert False
        except Stepping:
            assert True
    finally:
        monkeypatch.undo()

def test_primitive_be_display():
    assert space.objtable["w_display"] is None
    mock_display = model.W_PointersObject(space, space.w_Point, 4)
    w_wordbmp = model.W_WordsObject(space, space.w_Array, 10)
    mock_display.store(space, 0, w_wordbmp) # bitmap
    mock_display.store(space, 1, space.wrap_int(32)) # width
    mock_display.store(space, 2, space.wrap_int(10)) # height
    mock_display.store(space, 3, space.wrap_int(1))  # depth
    prim(primitives.BE_DISPLAY, [mock_display])
    assert space.objtable["w_display"] is mock_display
    w_bitmap = mock_display.fetch(space, 0)
    assert w_bitmap is not w_wordbmp
    assert isinstance(w_bitmap, model_display.W_DisplayBitmap)
    sdldisplay = w_bitmap.display
    assert isinstance(sdldisplay, display.SDLDisplay)

    mock_display2 = model.W_PointersObject(space, space.w_Point, 4)
    mock_display2.store(space, 0, model.W_WordsObject(space, space.w_Array, 10)) # bitmap
    mock_display2.store(space, 1, space.wrap_int(32)) # width
    mock_display2.store(space, 2, space.wrap_int(10)) # height
    mock_display2.store(space, 3, space.wrap_int(1))  # depth
    prim(primitives.BE_DISPLAY, [mock_display2])
    assert space.objtable["w_display"] is mock_display2
    w_bitmap2 = mock_display.fetch(space, 0)
    assert isinstance(w_bitmap2, model_display.W_DisplayBitmap)
    assert w_bitmap.display is w_bitmap2.display
    assert sdldisplay.width == 32
    assert sdldisplay.height == 10

    prim(primitives.BE_DISPLAY, [mock_display])
    assert space.objtable["w_display"] is mock_display
    assert mock_display.fetch(space, 0) is w_bitmap

def test_primitive_force_display_update(monkeypatch):
    mock_display = model.W_PointersObject(space, space.w_Point, 4)
    w_wordbmp = model.W_WordsObject(space, space.w_Array, 10)
    mock_display.store(space, 0, w_wordbmp) # bitmap
    mock_display.store(space, 1, space.wrap_int(32)) # width
    mock_display.store(space, 2, space.wrap_int(10)) # height
    mock_display.store(space, 3, space.wrap_int(1))  # depth
    prim(primitives.BE_DISPLAY, [mock_display])

    class DisplayFlush(Exception):
        pass

    def flush_to_screen_mock(self, force=False):
        raise DisplayFlush

    try:
        monkeypatch.setattr(space.display().__class__, "flip", flush_to_screen_mock)
        with py.test.raises(DisplayFlush):
            prim(primitives.FORCE_DISPLAY_UPDATE, [mock_display])
    finally:
        monkeypatch.undo()

def test_bitblt_copy_bits(monkeypatch):
    class CallCopyBitsSimulation(Exception):
        pass
    class Image():
        def __init__(self):
            self.w_simulateCopyBits = "simulateCopyBits"

    mock_bitblt = model.W_PointersObject(space, space.w_Point, 15)
    mock_bitblt.store(space, 3, space.wrap_int(15)) # combination rule

    def perform_mock(w_selector, argcount, interp):
        if w_selector == "simulateCopyBits" or w_selector.as_string() == "simulateCopyBits":
            assert argcount == 0
            raise CallCopyBitsSimulation

    def sync_cache_mock(self):
        raise CallCopyBitsSimulation

    interp, w_frame, argument_count = mock(space, [mock_bitblt], None)
    if interp.image is None:
        interp.image = Image()

    try:
        monkeypatch.setattr(w_frame.shadow, "_sendSelfSelector", perform_mock)
        monkeypatch.setattr(bitblt.BitBltShadow, "strategy_switched", sync_cache_mock)
        with py.test.raises(CallCopyBitsSimulation):
            prim_table[primitives.BITBLT_COPY_BITS](interp, w_frame.as_context_get_shadow(space), argument_count-1)
    finally:
        monkeypatch.undo()
    assert w_frame.shadow.pop() is mock_bitblt # the receiver

# Note:
#   primitives.NEXT is unimplemented as it is a performance optimization
#   primitives.NEXT_PUT is unimplemented as it is a performance optimization
#   primitives.AT_END is unimplemented as it is a performance optimization
#   primitives.BLOCK_COPY is tested in test_interpreter
#   primitives.VALUE is tested in test_interpreter
#   primitives.VALUE_WITH_ARGS is tested in test_interpreter
#   primitives.OBJECT_AT is tested in test_interpreter
#   primitives.OBJECT_AT_PUT is tested in test_interpreter
