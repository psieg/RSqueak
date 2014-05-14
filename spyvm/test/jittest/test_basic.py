import py

from .base import BaseJITTest

class TestBasic(BaseJITTest):
    def test_while_loop(self, spy, tmpdir):
        traces = self.run(spy, tmpdir, """
        0 to: 1000000000 do: [:t|nil].
        """)
        self.assert_matches(traces[0].loop, """
         i58 = int_le(i50, 1000000000),
         guard_true(i58, descr=<Guard0x2f17250>),
         i59 = int_add(i50, 1),
         i60 = int_sub(i54, 1),
         setfield_gc(ConstPtr(ptr51), i60, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
         i61 = int_le(i60, 0),
         guard_false(i61, descr=<Guard0x2f17210>),
         jump(p0, i1, p3, i59, p12, p14, p16, p18, p20, p22, p24, p26, p28, p30, p32, p34, p36, p38, i60, descr=TargetToken(49337584))
        """)
        self.assert_matches(traces[0].bridges[0], """
         f19 = call(ConstClass(ll_time.ll_time_time), descr=<Callf 8 EF=4>),
         setfield_gc(ConstPtr(ptr20), 10000, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
         guard_no_exception(descr=<Guard0x3117450>),
         f23 = float_sub(f19, 1400072025.015000),
         f25 = float_mul(f23, 1000.000000),
         i26 = cast_float_to_int(f25),
         i28 = int_and(i26, 2147483647),
         i29 = getfield_gc(ConstPtr(ptr20), descr=<FieldS spyvm.interpreter.Interpreter.inst_next_wakeup_tick 36>),
         i30 = int_is_zero(i29),
         guard_true(i30, descr=<Guard0x3117ad0>),
         label(p0, i1, p2, i17, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, descr=TargetToken(51495504)),
         guard_class(p0, 23562720, descr=<Guard0x3117a90>),
         p32 = getfield_gc(p0, descr=<FieldP spyvm.shadow.MethodContextShadow.inst__w_method 44>),
         p33 = getfield_gc(p32, descr=<FieldP spyvm.model.W_CompiledMethod.inst_version 56>),
         guard_value(p32, ConstPtr(ptr34), descr=<Guard0x3117a50>),
         guard_value(p33, ConstPtr(ptr35), descr=<Guard0x3117a10>),
         i37 = int_le(i17, 1000000000),
         guard_true(i37, descr=<Guard0x31179d0>),
         i39 = int_add(i17, 1),
         setfield_gc(ConstPtr(ptr20), 9999, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
         jump(p0, i1, p2, i39, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, 9999, descr=TargetToken(51434784))
        """)

    def test_constant_string(self, spy, tmpdir):
        traces = self.run(spy, tmpdir, """
        | i |
        i := 0.
        [i <= 10000] whileTrue: [ i := i + 'a' size].
        ^ i
        """)
        self.assert_matches(traces[0].loop, """
         i76 = int_le(i68, 10000),
         guard_true(i76, descr=<Guard0x31c8990>),
         guard_not_invalidated(descr=<Guard0x31c8950>),
         i77 = int_add_ovf(i68, i67),
         guard_no_overflow(descr=<Guard0x31c8910>),
         i78 = int_sub(i71, 1),
         setfield_gc(ConstPtr(ptr65), i78, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
         i79 = int_le(i78, 0),
         guard_false(i79, descr=<Guard0x31c88d0>),
         jump(p0, i1, p3, i77, p12, p14, p16, p18, p20, p22, p24, p26, p28, p30, p32, p34, p36, p38, i67, i78, descr=TargetToken(52151536))
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
         i78 = int_le(i70, 100000),
         guard_true(i78, descr=<Guard0x1298350>),
         i79 = int_add(i70, 1),
         i80 = int_sub(i74, 1),
         setfield_gc(ConstPtr(ptr71), i80, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
         i81 = int_le(i80, 0),
         guard_false(i81, descr=<Guard0x1298310>),
         i83 = arraylen_gc(p64, descr=<ArrayU 1>),
         i84 = arraylen_gc(p66, descr=<ArrayU 1>),
         jump(p0, i1, p3, i79, p12, p14, p16, p18, p20, p22, p24, p26, p28, p30, p32, p34, p36, p38, i80, p64, p66, descr=TargetToken(19461888))
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
         i71 = int_le(i63, 100000),
         guard_true(i71, descr=<Guard0x2f174d0>),
         i72 = int_add(i63, 1),
         i73 = int_sub(i67, 1),
         setfield_gc(ConstPtr(ptr64), i73, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>),
         i74 = int_le(i73, 0),
         guard_false(i74, descr=<Guard0x2f17450>),
         jump(p0, i1, p3, i72, p8, p10, p12, p14, p20, p22, p24, p26, p28, p30, p32, p34, p36, p38, p40, p42, p44, p46, i73, descr=TargetToken(49338064))
        """)

    def test_bitblt_fillWhite(self, spy, tmpdir):
        # This used to have a call to array comparison in it
        traces = []
        retries = 10
        while len(traces) == 0 and retries > 0:
            retries -= 1
            traces = self.run(spy, tmpdir, """
            Display beDisplay. 1 to: 10000 do: [:i | Display fillWhite].
            """)
        self.assert_matches(traces[0].loop, """
            i596 = int_le(2, i152)
            guard_false(i596, descr=<Guard0x36fb910>)
            i597 = getfield_gc_pure(p587, descr=<FieldS spyvm.model.W_SmallInteger.inst_value 8>)
            i598 = int_add_ovf(i597, i161)
            guard_no_overflow(descr=<Guard0x36fb7d0>)
            i599 = getfield_gc_pure(p590, descr=<FieldS spyvm.model.W_SmallInteger.inst_value 8>)
            i600 = int_add_ovf(i599, i170)
            guard_no_overflow(descr=<Guard0x36fb690>)
            i601 = int_add_ovf(i175, 1)
            guard_no_overflow(descr=<Guard0x36fb5d0>)
            i602 = int_sub(i583, 1)
            setfield_gc(ConstPtr(ptr176), i602, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>)
            i603 = int_le(i602, 0)
            guard_false(i603, descr=<Guard0x36fb590>)
            i604 = int_le(i601, i186)
            guard_true(i604, descr=<Guard0x36fb2d0>)
            guard_not_invalidated(descr=<Guard0x36fb190>)
            i605 = getfield_gc_pure(p362, descr=<FieldS spyvm.model.W_SmallInteger.inst_value 8>)
            i606 = int_mod(i605, i223)
            i607 = int_rshift(i606, 31)
            i608 = int_and(i223, i607)
            i609 = int_add(i606, i608)
            i610 = int_add_ovf(1, i609)
            guard_no_overflow(descr=<Guard0x36f8b90>)
            i611 = int_ge(i609, 0)
            guard_true(i611, descr=<Guard0x36f8910>)
            i612 = int_lt(i609, i223)
            guard_true(i612, descr=<Guard0x36f88d0>)
            i613 = getarrayitem_gc(p246, i609, descr=<ArrayU 4>)
            i614 = uint_lt(i613, 0)
            guard_false(i614, descr=<Guard0x36f8850>)
            i615 = uint_lt(i613, 2147483647)
            guard_true(i615, descr=<Guard0x36fbbd0>)
            i616 = int_add_ovf(i605, i255)
            guard_no_overflow(descr=<Guard0x36f8790>)
            i617 = int_ge(i613, 0)
            guard_true(i617, descr=<Guard0x36f8450>)
            i618 = int_and(i613, i613)
            i619 = uint_lt(i618, 2147483647)
            guard_true(i619, descr=<Guard0x36f83d0>)
            i620 = int_add_ovf(i600, 1)
            guard_no_overflow(descr=<Guard0x36f8310>)
            i621 = int_ge(i600, 0)
            guard_true(i621, descr=<Guard0x36f5f10>)
            i622 = int_lt(i600, i289)
            guard_true(i622, descr=<Guard0x36f5ed0>)
            i623 = getarrayitem_raw(i291, i600, descr=<ArrayU 4>)
            i624 = uint_lt(i623, 0)
            guard_false(i624, descr=<Guard0x36f5e90>)
            i625 = uint_lt(i623, 2147483647)
            guard_true(i625, descr=<Guard0x36f5e50>)
            i626 = int_and(i326, i618)
            i627 = uint_lt(i626, 2147483647)
            guard_true(i627, descr=<Guard0x36f5350>)
            i628 = getarrayitem_raw(i291, i600, descr=<ArrayU 4>)
            i629 = uint_lt(i628, 0)
            guard_false(i629, descr=<Guard0x36f0690>)
            i630 = uint_lt(i628, 2147483647)
            guard_true(i630, descr=<Guard0x36f0650>)
            i631 = int_ge(i628, 0)
            guard_true(i631, descr=<Guard0x36f05d0>)
            i632 = int_and(i341, i628)
            i633 = uint_lt(i632, 2147483647)
            guard_true(i633, descr=<Guard0x36f0590>)
            i634 = int_ge(i626, 0)
            guard_true(i634, descr=<Guard0x36f0550>)
            i635 = int_or(i626, i632)
            i636 = uint_lt(i635, 2147483647)
            guard_true(i636, descr=<Guard0x36f04d0>)
            setarrayitem_raw(i291, i600, i635, descr=<ArrayU 4>)
            i638 = int_lshift(i600, 3)
            i639 = int_ge(i638, i289)
            guard_false(i639, descr=<Guard0x36e8f90>)
            i640 = uint_rshift(i635, i384)
            i641 = int_lshift(i635, i371)
            i642 = uint_rshift(i641, i384)
            i643 = int_lshift(i642, 8)
            i644 = int_or(i640, i643)
            i645 = int_lshift(i641, i371)
            i646 = uint_rshift(i645, i384)
            i647 = int_lshift(i646, 16)
            i648 = int_or(i644, i647)
            i649 = int_lshift(i645, i371)
            i650 = uint_rshift(i649, i384)
            i651 = int_lshift(i650, 24)
            i652 = int_or(i648, i651)
            i653 = int_lshift(i649, i371)
            setarrayitem_raw(18153472, i638, i652, descr=<ArrayU 4>)
            i654 = int_add(i638, 1)
            i655 = int_ge(i654, i289)
            guard_false(i655, descr=<Guard0x36e8e90>)
            i656 = uint_rshift(i653, i384)
            i657 = int_lshift(i653, i371)
            i658 = uint_rshift(i657, i384)
            i659 = int_lshift(i658, 8)
            i660 = int_or(i656, i659)
            i661 = int_lshift(i657, i371)
            i662 = uint_rshift(i661, i384)
            i663 = int_lshift(i662, 16)
            i664 = int_or(i660, i663)
            i665 = int_lshift(i661, i371)
            i666 = uint_rshift(i665, i384)
            i667 = int_lshift(i666, 24)
            i668 = int_or(i664, i667)
            i669 = int_lshift(i665, i371)
            setarrayitem_raw(18153472, i654, i668, descr=<ArrayU 4>)
            i670 = int_add(i654, 1)
            i671 = int_ge(i670, i289)
            guard_false(i671, descr=<Guard0x36e8dd0>)
            i672 = uint_rshift(i669, i384)
            i673 = int_lshift(i669, i371)
            i674 = uint_rshift(i673, i384)
            i675 = int_lshift(i674, 8)
            i676 = int_or(i672, i675)
            i677 = int_lshift(i673, i371)
            i678 = uint_rshift(i677, i384)
            i679 = int_lshift(i678, 16)
            i680 = int_or(i676, i679)
            i681 = int_lshift(i677, i371)
            i682 = uint_rshift(i681, i384)
            i683 = int_lshift(i682, 24)
            i684 = int_or(i680, i683)
            i685 = int_lshift(i681, i371)
            setarrayitem_raw(18153472, i670, i684, descr=<ArrayU 4>)
            i686 = int_add(i670, 1)
            i687 = int_ge(i686, i289)
            guard_false(i687, descr=<Guard0x36e8d10>)
            i688 = uint_rshift(i685, i384)
            i689 = int_lshift(i685, i371)
            i690 = uint_rshift(i689, i384)
            i691 = int_lshift(i690, 8)
            i692 = int_or(i688, i691)
            i693 = int_lshift(i689, i371)
            i694 = uint_rshift(i693, i384)
            i695 = int_lshift(i694, 16)
            i696 = int_or(i692, i695)
            i697 = int_lshift(i693, i371)
            i698 = uint_rshift(i697, i384)
            i699 = int_lshift(i698, 24)
            i700 = int_or(i696, i699)
            i701 = int_lshift(i697, i371)
            setarrayitem_raw(18153472, i686, i700, descr=<ArrayU 4>)
            i702 = int_add(i686, 1)
            i703 = int_ge(i702, i289)
            guard_false(i703, descr=<Guard0x36e8c50>)
            i704 = uint_rshift(i701, i384)
            i705 = int_lshift(i701, i371)
            i706 = uint_rshift(i705, i384)
            i707 = int_lshift(i706, 8)
            i708 = int_or(i704, i707)
            i709 = int_lshift(i705, i371)
            i710 = uint_rshift(i709, i384)
            i711 = int_lshift(i710, 16)
            i712 = int_or(i708, i711)
            i713 = int_lshift(i709, i371)
            i714 = uint_rshift(i713, i384)
            i715 = int_lshift(i714, 24)
            i716 = int_or(i712, i715)
            i717 = int_lshift(i713, i371)
            setarrayitem_raw(18153472, i702, i716, descr=<ArrayU 4>)
            i718 = int_add(i702, 1)
            i719 = int_ge(i718, i289)
            guard_false(i719, descr=<Guard0x36e8b90>)
            i720 = uint_rshift(i717, i384)
            i721 = int_lshift(i717, i371)
            i722 = uint_rshift(i721, i384)
            i723 = int_lshift(i722, 8)
            i724 = int_or(i720, i723)
            i725 = int_lshift(i721, i371)
            i726 = uint_rshift(i725, i384)
            i727 = int_lshift(i726, 16)
            i728 = int_or(i724, i727)
            i729 = int_lshift(i725, i371)
            i730 = uint_rshift(i729, i384)
            i731 = int_lshift(i730, 24)
            i732 = int_or(i728, i731)
            i733 = int_lshift(i729, i371)
            setarrayitem_raw(18153472, i718, i732, descr=<ArrayU 4>)
            i734 = int_add(i718, 1)
            i735 = int_ge(i734, i289)
            guard_false(i735, descr=<Guard0x36e8ad0>)
            i736 = uint_rshift(i733, i384)
            i737 = int_lshift(i733, i371)
            i738 = uint_rshift(i737, i384)
            i739 = int_lshift(i738, 8)
            i740 = int_or(i736, i739)
            i741 = int_lshift(i737, i371)
            i742 = uint_rshift(i741, i384)
            i743 = int_lshift(i742, 16)
            i744 = int_or(i740, i743)
            i745 = int_lshift(i741, i371)
            i746 = uint_rshift(i745, i384)
            i747 = int_lshift(i746, 24)
            i748 = int_or(i744, i747)
            i749 = int_lshift(i745, i371)
            setarrayitem_raw(18153472, i734, i748, descr=<ArrayU 4>)
            i750 = int_add(i734, 1)
            i751 = int_ge(i750, i289)
            guard_false(i751, descr=<Guard0x36e8a10>)
            i752 = uint_rshift(i749, i384)
            i753 = int_lshift(i749, i371)
            i754 = uint_rshift(i753, i384)
            i755 = int_lshift(i754, 8)
            i756 = int_or(i752, i755)
            i757 = int_lshift(i753, i371)
            i758 = uint_rshift(i757, i384)
            i759 = int_lshift(i758, 16)
            i760 = int_or(i756, i759)
            i761 = int_lshift(i757, i371)
            i762 = uint_rshift(i761, i384)
            i763 = int_lshift(i762, 24)
            i764 = int_or(i760, i763)
            i765 = int_lshift(i761, i371)
            setarrayitem_raw(18153472, i750, i764, descr=<ArrayU 4>)
            i766 = int_add(i750, 1)
            i767 = int_add_ovf(i598, i569)
            guard_no_overflow(descr=<Guard0x36e8850>)
            i768 = int_add_ovf(i600, i569)
            guard_no_overflow(descr=<Guard0x36e8810>)
            i769 = int_sub(i602, 10)
            setfield_gc(ConstPtr(ptr176), i769, descr=<FieldS spyvm.interpreter.Interpreter.inst_interrupt_check_counter 24>)
            i770 = int_le(i769, 0)
            guard_false(i770, descr=<Guard0x36e8690>)
            p771 = new_with_vtable(23559752)
            setfield_gc(p771, i767, descr=<FieldS spyvm.model.W_SmallInteger.inst_value 8>)
            setarrayitem_gc(p146, 34, p771, descr=<ArrayP 4>)
            p772 = new_with_vtable(23559752)
            setfield_gc(p772, i768, descr=<FieldS spyvm.model.W_SmallInteger.inst_value 8>)
            setarrayitem_gc(p146, 35, p772, descr=<ArrayP 4>)
            p773 = new_with_vtable(23559752)
            setfield_gc(p773, i616, descr=<FieldS spyvm.model.W_SmallInteger.inst_value 8>)
            setarrayitem_gc(p146, 20, p773, descr=<ArrayP 4>)
            i774 = arraylen_gc(p146, descr=<ArrayP 4>)
            i775 = arraylen_gc(p579, descr=<ArrayP 4>)
            jump(p0, i1, p3, p8, i613, p594, i618, p18, i601, p38, p40, p42, p44, p46, p48, p50, p52, p54, p56, p58, p60, p62, p64, p66, p68, p70, p72, p74, p76, p78, p80, p82, p84, p86, p88, p90, p92, p94, p96, p98, p100, p102, p104, p106, p108, p110, p112, p114, p116, p118, p120, p122, p124, p126, p128, p130, p132, p134, 1, p148, p771, i161, p157, p772, i170, p166, p146, i769, i186, p183, p189, p773, i223, p199, p246, i255, p253, p262, p141, p280, i289, i291, i326, i341, i384, i371, i569, p567, p594, p579, descr=TargetToken(57116320))          
        """)
        
    @py.test.mark.skipif("'just dozens of long traces'")
    def test_bitblt_draw_windows(self, spy, tmpdir):
        # This used to have a call to array comparison in it
        traces = self.run(spy, tmpdir, """
        Display beDisplay.
        1 to: 100 do: [:i | ControlManager startUp].
        """)
        self.assert_matches(traces[0].loop, """
        """)
