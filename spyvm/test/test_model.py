import py, math, socket
from spyvm import model, model_display, storage_classes, error, display
from rpython.rlib.rarithmetic import intmask, r_uint
from rpython.rtyper.lltypesystem import lltype, rffi
from .util import create_space, copy_to_module, cleanup_module

def setup_module():
    space = create_space(bootstrap = True)
    bootstrap_class = space.bootstrap_class
    w_foo = space.wrap_string("foo")
    w_bar = space.wrap_string("bar")
    copy_to_module(locals(), __name__)

def teardown_module():
    cleanup_module(__name__)

def joinbits(values, lengths):
    result = 0
    for each, length in reversed(zip(values, lengths)):
        result = result << length
        result += each
    return result

def test_new():
    w_mycls = bootstrap_class(0)
    w_myinstance = w_mycls.as_class_get_shadow(space).new()
    assert isinstance(w_myinstance, model.W_PointersObject)
    assert w_myinstance.getclass(space).is_same_object(w_mycls)
    assert w_myinstance.class_shadow(space) is w_mycls.as_class_get_shadow(space)

def test_new_namedvars():
    w_mycls = bootstrap_class(3)
    w_myinstance = w_mycls.as_class_get_shadow(space).new()

    w_myinstance.store(space, 0, w_myinstance) # Make sure ListStorage is used
    w_myinstance.store(space, 0, space.w_nil)

    assert isinstance(w_myinstance, model.W_PointersObject)
    assert w_myinstance.getclass(space).is_same_object(w_mycls)
    assert w_myinstance.fetch(space, 0).is_nil(space)
    py.test.raises(IndexError, lambda: w_myinstance.fetch(space, 3))
    w_myinstance.store(space, 1, w_myinstance)
    assert w_myinstance.fetch(space, 1) is w_myinstance

def test_bytes_object():
    w_class = bootstrap_class(0, format=storage_classes.BYTES)
    w_bytes = w_class.as_class_get_shadow(space).new(20)
    assert w_bytes.getclass(space).is_same_object(w_class)
    assert w_bytes.size() == 20
    assert w_class.as_class_get_shadow(space).instsize() == 0
    assert w_bytes.getchar(3) == "\x00"
    w_bytes.setchar(3, "\xAA")
    assert w_bytes.getchar(3) == "\xAA"
    assert w_bytes.getchar(0) == "\x00"
    py.test.raises(IndexError, lambda: w_bytes.getchar(20))

@py.test.mark.skipif("'removed interpreter proxy'")
def test_c_bytes_object():
    w_class = bootstrap_class(0, format=storage_classes.BYTES)
    w_bytes = w_class.as_class_get_shadow(space).new(20)
    w_bytes.convert_to_c_layout()
    assert w_bytes.getclass(space).is_same_object(w_class)
    assert w_bytes.size() == 20
    assert w_class.as_class_get_shadow(space).instsize() == 0
    assert w_bytes.getchar(3) == "\x00"
    w_bytes.setchar(3, "\xAA")
    assert w_bytes.getchar(3) == "\xAA"
    assert w_bytes.getchar(0) == "\x00"
    py.test.raises(IndexError, lambda: w_bytes.getchar(20))

def test_word_object():
    w_class = bootstrap_class(0, format=storage_classes.WORDS)
    w_bytes = w_class.as_class_get_shadow(space).new(20)
    assert w_bytes.getclass(space).is_same_object(w_class)
    assert w_bytes.size() == 20
    assert w_class.as_class_get_shadow(space).instsize() == 0
    assert w_bytes.getword(3) == 0
    w_bytes.setword(3, 42)
    assert w_bytes.getword(3) == 42
    assert w_bytes.getword(0) == 0
    py.test.raises(AssertionError, lambda: w_bytes.getword(20))

@py.test.mark.skipif("'removed interpreter proxy'")
def test_c_word_object():
    w_class = bootstrap_class(0, format=storage_classes.WORDS)
    w_bytes = w_class.as_class_get_shadow(space).new(20)
    w_bytes.convert_to_c_layout()
    assert w_bytes.getclass(space).is_same_object(w_class)
    assert w_bytes.size() == 20
    assert w_class.as_class_get_shadow(space).instsize() == 0
    assert w_bytes.getword(3) == 0
    w_bytes.setword(3, 42)
    assert w_bytes.getword(3) == 42
    assert w_bytes.getword(0) == 0
    py.test.raises(AssertionError, lambda: w_bytes.getword(20))

def test_method_lookup():
    class mockmethod(object):
        def __init__(self, val):
            self.val = val
    w_class = bootstrap_class(0)
    shadow = w_class.as_class_get_shadow(space)
    shadow.installmethod(w_foo, mockmethod(1))
    shadow.installmethod(w_bar, mockmethod(2))
    w_subclass = bootstrap_class(0, w_superclass=w_class)
    subshadow = w_subclass.as_class_get_shadow(space)
    assert subshadow.s_superclass() is shadow
    subshadow.installmethod(w_foo, mockmethod(3))
    shadow.initialize_methoddict()
    subshadow.initialize_methoddict()
    assert shadow.lookup(w_foo).val == 1
    assert shadow.lookup(w_bar).val == 2
    py.test.raises(error.MethodNotFound, shadow.lookup, "zork")
    assert subshadow.lookup(w_foo).val == 3
    assert subshadow.lookup(w_bar).val == 2
    py.test.raises(error.MethodNotFound, subshadow.lookup, "zork")

def test_compiledin_class():
    w_super = bootstrap_class(0)
    w_class = bootstrap_class(0, w_superclass=w_super)
    supershadow = w_super.as_class_get_shadow(space)
    supershadow.installmethod(w_foo, model.W_CompiledMethod(space, 0))
    classshadow = w_class.as_class_get_shadow(space)
    classshadow.initialize_methoddict()
    assert classshadow.lookup(w_foo).compiled_in() is w_super

def new_object(size=0):
    return model.W_PointersObject(space, None, size)

def test_compiledin_class_assoc():
    val = bootstrap_class(0)
    assoc = new_object(2)
    assoc.store(space, 0, new_object())
    assoc.store(space, 1, val)
    meth = model.W_CompiledMethod(space, 0)
    meth.setliterals([new_object(), new_object(), assoc ])
    assert meth.compiled_in() == val

def test_compiledin_class_missing():
    meth = model.W_CompiledMethod(space, 0)
    meth.compiledin_class = None
    meth.setliterals([new_object(), new_object() ])
    assert meth.compiled_in() == None

def test_compiledmethod_setchar():
    w_method = model.W_CompiledMethod(space, 3)
    w_method.setchar(0, "c")
    assert w_method.bytes == list("c\x00\x00")

def test_hashes():
    w_five = model.W_SmallInteger(5)
    assert w_five.gethash() == 5
    w_class = bootstrap_class(0)
    w_inst = w_class.as_class_get_shadow(space).new()
    assert w_inst.hash == w_inst.UNASSIGNED_HASH
    h1 = w_inst.gethash()
    h2 = w_inst.gethash()
    assert h1 == h2
    assert h1 == w_inst.hash

def test_compiledmethod_at0():
    w_method = model.W_CompiledMethod(space, )
    w_method.bytes = list("abc")
    w_method.header = 100
    w_method.setliterals(['lit1', 'lit2'])
    w_method.literalsize = 2
    assert space.unwrap_int(w_method.at0(space, 0)) == 100
    assert w_method.at0(space, 4) == 'lit1'
    assert w_method.at0(space, 8) == 'lit2'
    assert space.unwrap_int(w_method.at0(space, 12)) == ord('a')
    assert space.unwrap_int(w_method.at0(space, 13)) == ord('b')
    assert space.unwrap_int(w_method.at0(space, 14)) == ord('c')

def test_compiledmethod_atput0():
    w_method = model.W_CompiledMethod(space, 3)
    newheader = joinbits([0,2,0,0,0,0],[9,8,1,6,4,1])
    assert w_method.getliteralsize() == 0
    w_method.atput0(space, 0, space.wrap_int(newheader))
    assert w_method.getliteralsize() == 8 # 2 from new header * BYTES_PER_WORD (= 4)
    w_method.atput0(space, 4, 'lit1')
    w_method.atput0(space, 8, 'lit2')
    w_method.atput0(space, 12, space.wrap_int(ord('a')))
    w_method.atput0(space, 13, space.wrap_int(ord('b')))
    w_method.atput0(space, 14, space.wrap_int(ord('c')))
    assert space.unwrap_int(w_method.at0(space, 0)) == newheader
    assert w_method.at0(space, 4) == 'lit1'
    assert w_method.at0(space, 8) == 'lit2'
    assert space.unwrap_int(w_method.at0(space, 12)) == ord('a')
    assert space.unwrap_int(w_method.at0(space, 13)) == ord('b')
    assert space.unwrap_int(w_method.at0(space, 14)) == ord('c')

def test_compiledmethod_atput0_not_aligned():
    header = joinbits([0,2,0,0,0,0],[9,8,1,6,4,1])
    w_method = model.W_CompiledMethod(space, 3, header)
    with py.test.raises(error.PrimitiveFailedError):
        w_method.atput0(space, 7, 'lit1')
    with py.test.raises(error.PrimitiveFailedError):
        w_method.atput0(space, 9, space.wrap_int(5))

def test_is_same_object(w_o1=None, w_o2=None):
    if w_o1 is None:
        w_o1 = model.W_PointersObject(space, None, 0)
    if w_o2 is None:
        w_o2 = w_o1
    assert w_o1.is_same_object(w_o2)
    assert w_o2.is_same_object(w_o1)

def test_not_is_same_object(w_o1=None,w_o2=None):
    if w_o1 is None:
        w_o1 = model.W_PointersObject(space, None, 0)
    if w_o2 is None:
        w_o2 = model.W_PointersObject(space, None,0)
    assert not w_o1.is_same_object(w_o2)
    assert not w_o2.is_same_object(w_o1)
    w_o2 = model.W_SmallInteger(2)
    assert not w_o1.is_same_object(w_o2)
    assert not w_o2.is_same_object(w_o1)
    w_o2 = model.W_Float(5.5)
    assert not w_o1.is_same_object(w_o2)
    assert not w_o2.is_same_object(w_o1)

def test_intfloat_is_same_object():
    test_is_same_object(model.W_SmallInteger(1), model.W_SmallInteger(1))
    test_is_same_object(model.W_SmallInteger(100), model.W_SmallInteger(100))
    test_is_same_object(model.W_Float(1.100), model.W_Float(1.100))

def test_intfloat_notis_same_object():
    test_not_is_same_object(model.W_SmallInteger(1), model.W_Float(1))
    test_not_is_same_object(model.W_Float(100), model.W_SmallInteger(100))
    test_not_is_same_object(model.W_Float(1.100), model.W_Float(1.200))
    test_not_is_same_object(model.W_SmallInteger(101), model.W_SmallInteger(100))

def test_charis_same_object():
    test_is_same_object(space.wrap_char('a'), space.wrap_char('a'))
    test_is_same_object(space.wrap_char('d'), space.wrap_char('d'))

def test_not_charis_same_object():
    test_not_is_same_object(space.wrap_char('a'), space.wrap_char('d'))
    test_not_is_same_object(space.wrap_char('d'), space.wrap_int(3))
    test_not_is_same_object(space.wrap_char('d'), space.wrap_float(3.0))

def test_become_pointers():
    w_clsa = bootstrap_class(3)
    w_a = w_clsa.as_class_get_shadow(space).new()

    w_clsb = bootstrap_class(4)
    w_b = w_clsb.as_class_get_shadow(space).new()

    hasha = w_a.gethash()
    hashb = w_b.gethash()

    w_a.store(space, 0, w_b)
    w_b.store(space, 1, w_a)

    res = w_a.become(w_b)
    assert res
    assert w_a.gethash() == hashb
    assert w_b.gethash() == hasha

    assert w_a.getclass(space).is_same_object(w_clsb)
    assert w_b.getclass(space).is_same_object(w_clsa)

    assert w_b.fetch(space, 0) is w_b
    assert w_a.fetch(space, 1) is w_a

def test_become_with_shadow():
    w_clsa = bootstrap_class(3)
    s_clsa = w_clsa.as_class_get_shadow(space)
    w_clsb = bootstrap_class(4)
    s_clsb = w_clsb.as_class_get_shadow(space)
    res = w_clsa.become(w_clsb)
    assert res
    assert w_clsa.as_class_get_shadow(space) is s_clsb
    assert s_clsa._w_self is w_clsb
    assert w_clsb.as_class_get_shadow(space) is s_clsa
    assert s_clsb._w_self is w_clsa

def test_word_atput():
    i = model.W_SmallInteger(100)
    b = model.W_WordsObject(space, None, 1)
    b.atput0(space, 0, i)
    assert 100 == b.getword(0)
    i = space.classtable['w_LargePositiveInteger'].as_class_get_shadow(space).new(4)
    i.atput0(space, 3, space.wrap_int(192))
    b.atput0(space, 0, i)
    assert b.getword(0) == 3221225472

def test_word_at():
    b = model.W_WordsObject(space, None, 1)
    b.setword(0, 100)
    r = b.at0(space, 0)
    assert isinstance(r, model.W_SmallInteger)
    assert space.unwrap_int(r) == 100

    b.setword(0, 3221225472)
    r = b.at0(space, 0)
    assert isinstance(r, (model.W_BytesObject, model.W_LargePositiveInteger1Word))
    assert r.size() == 4

def test_float_at():
    b = model.W_Float(64.0)
    r = b.fetch(space, 0)
    if isinstance(r, model.W_LargePositiveInteger1Word):
        assert r.size() == 4
        assert space.unwrap_int(r.at0(space, 0)) == 0
        assert space.unwrap_int(r.at0(space, 1)) == 0
        assert space.unwrap_int(r.at0(space, 2)) == 80
        assert space.unwrap_int(r.at0(space, 3)) == 64
    else:
        assert isinstance(r, model.W_SmallInteger)
        assert space.unwrap_int(r) == (80 << 16) + (64 << 24)
    r = b.fetch(space, 1)
    assert isinstance(r, model.W_SmallInteger)
    assert r.value == 0

def test_float_at_put():
    target = model.W_Float(1.0)
    for f in [1.0, -1.0, 1.1, 64.4, -0.0, float('nan'), float('inf')]:
        source = model.W_Float(f)
        target.store(space, 0, source.fetch(space, 0))
        target.store(space, 1, source.fetch(space, 1))
        if math.isnan(f):
            assert math.isnan(target.value)
        else:
            assert target.value == f

def test_float_hash():
    target = model.W_Float(1.1)
    assert target.gethash() == model.W_Float(1.1).gethash()
    target.store(space, 0, space.wrap_int(42))
    assert target.gethash() != model.W_Float(1.1).gethash()

def test_large_positive_integer_1word_at():
    b = model.W_LargePositiveInteger1Word(-1)
    for i in range(4):
        r = b.at0(space, i)
        assert isinstance(r, model.W_SmallInteger)
        assert space.unwrap_int(r) == 0xff
    assert b.value == -1

def test_large_positive_integer_1word_at_put():
    target = model.W_LargePositiveInteger1Word(0)
    source = model.W_LargePositiveInteger1Word(-1)
    for i in range(4):
        target.atput0(space, i, source.at0(space, i))
        assert target.at0(space, i) == source.at0(space, i)
    assert hex(r_uint(target.value)) == hex(r_uint(source.value))

def test_BytesObject_short_at():
    target = model.W_BytesObject(space, None, 4)
    target.setchar(0, chr(0x00))
    target.setchar(1, chr(0x01))
    target.setchar(2, chr(0x10))
    target.setchar(3, chr(0x81))
    assert target.short_at0(space, 0).value == 0x0100
    assert target.short_at0(space, 1).value == intmask(0xffff8110)

def test_BytesObject_short_atput():
    target = model.W_BytesObject(space, None, 4)
    target.short_atput0(space, 0, space.wrap_int(0x0100))
    target.short_atput0(space, 1, space.wrap_int(intmask(0xffff8110)))
    assert target.getchar(0) == chr(0x00)
    assert target.getchar(1) == chr(0x01)
    assert target.getchar(2) == chr(0x10)
    assert target.getchar(3) == chr(0x81)

def test_WordsObject_short_at():
    target = model.W_WordsObject(space, None, 2)
    target.setword(0, r_uint(0x00018000))
    target.setword(1, r_uint(0x80010111))
    assert target.short_at0(space, 0).value == intmask(0xffff8000)
    assert target.short_at0(space, 1).value == intmask(0x0001)
    assert target.short_at0(space, 2).value == intmask(0x0111)
    assert target.short_at0(space, 3).value == intmask(0xffff8001)

def test_WordsObject_short_atput():
    target = model.W_WordsObject(space, None, 2)
    target.short_atput0(space, 0, space.wrap_int(0x0100))
    target.short_atput0(space, 1, space.wrap_int(-1))
    target.short_atput0(space, 2, space.wrap_int(intmask(0xffff8000)))
    target.short_atput0(space, 3, space.wrap_int(0x7fff))
    assert target.getword(0) == 0xffff0100
    assert target.getword(1) == 0x7fff8000

def test_display_bitmap():
    size = 10
    space.display().set_video_mode(32, size, 1)
    target = model_display.W_MappingDisplayBitmap(space, space.w_Array, size, 1)
    for idx in range(size):
        target.setword(idx, r_uint(0))
    target.take_over_display()

    target.setword(0, r_uint(0xFF00))
    assert bin(target.getword(0)) == bin(0xFF00)
    target.setword(0, r_uint(0x00FF00FF))
    assert bin(target.getword(0)) == bin(0x00FF00FF)
    target.setword(0, r_uint(0xFF00FF00))
    assert bin(target.getword(0)) == bin(0xFF00FF00)

    buf = target.pixelbuffer()
    for i in xrange(2):
        assert buf[i] == 0x01010101
    for i in xrange(2, 4):
        assert buf[i] == 0x0
    for i in xrange(4, 6):
        assert buf[i] == 0x01010101
    for i in xrange(6, 8):
        assert buf[i] == 0x0

def test_display_offset_computation_even():
    dbitmap = model_display.W_MappingDisplayBitmap(space, space.w_Array, 200, 1)
    dbitmap.pitch = 64
    dbitmap.words_per_line = 2
    assert dbitmap.compute_pos(0) == 0
    assert dbitmap.compute_pos(1) == 32
    assert dbitmap.compute_pos(2) == 64

def test_display_offset_computation_uneven():
    dbitmap = model_display.W_MappingDisplayBitmap(space, space.w_Array, 200, 1)
    dbitmap.pitch = 67
    dbitmap.words_per_line = 2
    assert dbitmap.compute_pos(0) == 0
    assert dbitmap.compute_pos(1) == 32
    assert dbitmap.compute_pos(2) == 67
    assert dbitmap.compute_pos(3) == 67 + 32

def test_weak_pointers():
    w_cls = bootstrap_class(2)
    s_cls = w_cls.as_class_get_shadow(space)
    s_cls.instance_kind = storage_classes.WEAK_POINTERS

    weak_object = s_cls.new()
    referenced = model.W_SmallInteger(10)
    referenced2 = model.W_SmallInteger(20)
    weak_object.store(space, 0, referenced)
    weak_object.store(space, 1, referenced2)

    assert weak_object.fetch(space, 0) is referenced
    del referenced
    # When executed using pypy, del is not immediately executed.
    # Thus the reference may linger until the next gc...
    import gc; gc.collect()
    assert weak_object.fetch(space, 0).is_nil(space)
    assert weak_object.fetch(space, 1).value == 20
