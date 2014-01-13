import py

from .base import BaseJITTest


class TestBasic(BaseJITTest):
    def test_while_loop(self, spy, tmpdir):
        traces = self.run(spy, tmpdir, """
        0 to: 10000000 do: [:t|nil].
        """)
        self.assert_matches(traces[0].loop, """
        guard_not_invalidated(descr=<Guard0x1ba06b0>),
        i57 = int_le(i50, 10000000),
        guard_true(i57, descr=<Guard0x1ba0640>),
        i58 = int_add(i50, 1),
        i59 = int_sub(i54, 1),
        setfield_gc(ConstPtr(ptr51), i59, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
        i60 = int_le(i59, 0),
        guard_false(i60, descr=<Guard0x1ba05d0>),
        jump(p0, i3, p4, i58, p13, p15, p17, p19, p21, p23, p25, p27, p29, p31, p33, p35, p37, p39, i59, descr=TargetToken(27868504))
        """)
        self.assert_matches(traces[0].bridges[0], """
        f19 = call(ConstClass(ll_time.ll_time_time), descr=<Callf 8 EF=4>),
        setfield_gc(ConstPtr(ptr20), 10000, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
        guard_no_exception(descr=<Guard0x3596800>),
        f23 = float_mul(f19, 1000.000000),
        i24 = cast_float_to_int(f23),
        i26 = int_sub(i24, 1389627640615),
        i27 = getfield_gc(ConstPtr(ptr20), descr=<FieldS spyvm.interpreter.Interpreter.inst_next_wakeup_tick 48>),
        i28 = int_is_zero(i27),
        guard_true(i28, descr=<Guard0x35a8330>),
        label(p0, i1, p2, i17, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, descr=TargetToken(55082592)),
        guard_class(p0, ConstClass(MethodContextShadow), descr=<Guard0x35a82c0>),
        p30 = getfield_gc(p0, descr=<FieldP spyvm.shadow.MethodContextShadow.inst__w_method 88>),
        guard_value(p30, ConstPtr(ptr31), descr=<Guard0x35a8250>),
        guard_not_invalidated(descr=<Guard0x35a81e0>),
        i33 = int_le(i17, 10000000),
        guard_true(i33, descr=<Guard0x35a8170>),
        i35 = int_add(i17, 1),
        setfield_gc(ConstPtr(ptr20), 9999, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
        jump(p0, i1, p2, i35, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, 9999, descr=TargetToken(55082328))
        """)

    def test_constant_string(self, spy, tmpdir):
        traces = self.run(spy, tmpdir, """
        | i |
        i := 0.
        [i <= 10000] whileTrue: [ i := i + 'a' size].
        ^ i
        """)
        self.assert_matches(traces[0].loop, """
        guard_not_invalidated(descr=<Guard0x2f3b750>),
        i65 = int_le(i59, 10000),
        guard_true(i65, descr=<Guard0x2f3b6e0>),
        i66 = int_add(i59, 1),
        i67 = int_sub(i62, 1),
        setfield_gc(ConstPtr(ptr56), i67, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
        i68 = int_le(i67, 0),
        guard_false(i68, descr=<Guard0x2f3b670>),
        jump(p0, i3, p4, i66, p13, p15, p17, p19, p21, p23, p25, p27, p29, p31, p33, p35, p37, p39, i67, descr=TargetToken(48782592))
        """)

    def test_constant_string_equal2(self, spy, tmpdir):
        # This used to have a call to array comparison in it
        traces = self.run(spy, tmpdir, """
        | i |
        i := 0.
        [i <= 100000] whileTrue: [
          'a' == 'ab'.
          'cde' == 'efg'.
          'hij' == 'hij'.
          i := i + 1].
        ^ i
        """)
        self.assert_matches(traces[0].loop, """
        guard_not_invalidated(descr=<Guard0x27c6560>),
        i73 = int_le(i66, 100000),
        guard_true(i73, descr=<Guard0x27c64f0>),
        i74 = int_add(i66, 1),
        i75 = int_sub(i70, 2),
        setfield_gc(ConstPtr(ptr67), i75, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
        i76 = int_le(i75, 0),
        guard_false(i76, descr=<Guard0x27c6480>),
        i78 = arraylen_gc(p50, descr=<ArrayU 1>),
        i79 = arraylen_gc(p54, descr=<ArrayU 1>),
        i80 = arraylen_gc(p58, descr=<ArrayU 1>),
        jump(p0, i3, p4, i74, p13, p15, p17, p19, p21, p23, p25, p27, p29, p31, p33, p35, p37, p39, i75, p50, p54, p58, descr=TargetToken(40565840))
        """)

    def test_constant_string_var_equal(self, spy, tmpdir):
        # This used to have a call to array comparison in it
        traces = self.run(spy, tmpdir, """
        | i a b c d |
        i := 0.
        a = 'a'.
        b = 'bc'.
        c = 'cd'.
        d = 'bc'.
        [i <= 100000] whileTrue: [
          a == b.
          b == c.
          b == d.
          i := i + 1].
        ^ i
        """)
        self.assert_matches(traces[0].loop, """
        guard_not_invalidated(descr=<Guard0x33981e0>),
        i70 = int_le(i63, 100000),
        guard_true(i70, descr=<Guard0x3398170>),
        i71 = int_add(i63, 1),
        i72 = int_sub(i67, 1),
        setfield_gc(ConstPtr(ptr64), i72, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
        i73 = int_le(i72, 0),
        guard_false(i73, descr=<Guard0x3398100>),
        jump(p0, i3, p4, i71, p9, p11, p13, p15, p21, p23, p25, p27, p29, p31, p33, p35, p37, p39, p41, p43, p45, p47, i72, descr=TargetToken(52952232))
        """)

    def test_bitInvert32(self, spy, tmpdir):
        traces = self.run(spy, tmpdir, """
        | srcWord dstWord |
        srcWord := 16rCAFFEE.
        1 to: 1000000 do: [:t|
          srcWord := srcWord bitInvert32.
        ].
        """)
        self.assert_matches(traces[0].loop, """
        guard_not_invalidated(descr=<Guard0x2a59750>),
        i83 = int_le(i76, 1000000),
        guard_true(i83, descr=<Guard0x2a596e0>),
        setfield_gc(ConstPtr(ptr61), i68, descr=<FieldS spyvm.interpreter.Interpreter.inst_remaining_stack_depth 56>),
        i84 = int_ge(i74, 0),
        guard_true(i84, descr=<Guard0x2a59670>),
        i85 = int_xor(i74, i73),
        i86 = int_add(i76, 1),
        i87 = int_sub(i79, 3),
        setfield_gc(ConstPtr(ptr61), i64, descr=<FieldS spyvm.interpreter.Interpreter.inst_remaining_stack_depth 56>),
        setfield_gc(ConstPtr(ptr61), i87, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
        i88 = int_le(i87, 0),
        guard_false(i88, descr=<Guard0x2a59600>),
        jump(p0, i3, p4, i85, p9, i86, p17, p19, p21, p23, p25, p27, p29, p31, p33, p35, p37, p39, p41, p43, i68, i53, i73, i87, i64, descr=TargetToken(43310512))
        """)

    def test_bitXor(self, spy, tmpdir):
        traces = self.run(spy, tmpdir, """
        | srcWord dstWord |
        srcWord := 16rCAFFEE.
        dstWord := 16r987654.
        1 to: 1000000 do: [:t|
          srcWord := srcWord bitXor: dstWord.
        ].
        """)
        self.assert_matches(traces[0].loop, """
        guard_not_invalidated(descr=<Guard0x2dc3d70>),
        i75 = int_le(i69, 1000000),
        guard_true(i75, descr=<Guard0x2dc3d00>),
        i76 = int_xor(i67, i64),
        i77 = int_add(i69, 1),
        i78 = int_sub(i72, 1),
        setfield_gc(ConstPtr(ptr58), i78, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
        i79 = int_le(i78, 0),
        guard_false(i79, descr=<Guard0x2dc3c90>),
        jump(p0, i3, p4, i76, p9, i77, p17, p19, p21, p23, p25, p27, p29, p31, p33, p35, p37, p39, p41, p43, i64, i78, descr=TargetToken(46857208))
        """)

    def test_DisplayFlash(self, spy, tmpdir):
        traces = self.run(spy, tmpdir, """
        | path |
        Display
            setExtent: 200@200;
            beDisplay;
            fillWhite.
        path := OrderedCollection new: 16.
        #(40 115 190 265) do: [:y |
            #(60 160 260 360) do: [:x |
                path add: x@y]].
        1 to: 16 do: [:index |
            BitBlt exampleAt: (path at: index) rule: index - 1 fillColor: nil].
        """)
        self.assert_matches(traces[0].loop, """
        guard_not_invalidated(descr=<Guard0x1898410>),
        i74 = int_le(i68, 1000000),
        guard_true(i74, descr=<Guard0x18983a0>),
        i75 = int_xor(i66, i63),
        i76 = int_add(i68, 1),
        i77 = int_sub(i71, 1),
        setfield_gc(ConstPtr(ptr57), i77, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
        i78 = int_le(i77, 0),
        guard_false(i78, descr=<Guard0x1898330>),
        jump(p0, p3, i75, p8, i76, p16, p18, p20, p22, p24, p26, p28, p30, p32, p34, p36, p38, p40, p42, i63, i77, descr=TargetToken(24673448))
        """)
