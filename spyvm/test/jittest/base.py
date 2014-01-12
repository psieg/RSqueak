import subprocess
import os
import sys

# TODO:
from pypy.tool.jitlogparser.parser import SimpleParser, Op
from pypy.tool.jitlogparser.storage import LoopStorage

from rpython.jit.metainterp.test.support import LLJitMixin
from rpython.jit.metainterp.resoperation import opname
from rpython.jit.tool import oparser
from rpython.tool import logparser
from rpython import conftest

class o:
    view = False
    viewloops = True
conftest.option = o


sys.setrecursionlimit(5000)
# expose the bytecode's values as global constants.
# Bytecodes that have a whole range are exposed as global functions:
# call them with an argument 'n' to get the bytecode number 'base + n'.
# XXX hackish
def setup():
    from spyvm import interpreter
    def make_getter(entry):
        def get_opcode_chr(n):
            opcode = entry[0] + n
            assert entry[0] <= opcode <= entry[1]
            return chr(opcode)
        return get_opcode_chr
    for entry in interpreter.BYTECODE_RANGES:
        name = entry[-1]
        if len(entry) == 2:     # no range
            globals()[name] = chr(entry[0])
        else:
            globals()[name] = make_getter(entry)
setup()


BasePath = os.path.abspath(
    os.path.join(
        os.path.join(os.path.dirname(__file__), os.path.pardir),
        os.path.pardir,
        os.path.pardir
    )
)
BenchmarkImage = os.path.join(os.path.dirname(__file__), "benchmark.image")

class BaseJITTest(LLJitMixin):
    def run(self, spy, tmpdir, code):
        code = code.replace("\n", "\r\n")
        if spy:
            return self.run_binary(spy, tmpdir, code)
        else:
            return self.run_simulated(tmpdir, code)

    def run_binary(self, spy, tmpdir, code):
        proc = subprocess.Popen(
            [str(spy), "-r", code, BenchmarkImage],
            cwd=str(tmpdir),
            env={"PYPYLOG": "jit-log-opt:%s" % tmpdir.join("x.pypylog")}
        )
        proc.wait()
        data = logparser.parse_log_file(str(tmpdir.join("x.pypylog")), verbose=False)
        data = logparser.extract_category(data, "jit-log-opt-")

        storage = LoopStorage()
        traces = [SimpleParser.parse_from_input(t) for t in data]
        main_loops = storage.reconnect_loops(traces)
        traces_w = []
        for trace in traces:
            if trace in main_loops:
                traces_w.append(Trace(trace))
            else:
                traces_w[len(traces_w) - 1].addbridge(trace)
        return traces_w

    def run_simulated(self, tmpdir, code):
        import targetimageloadingsmalltalk

        info = {"interpreter": None, "selector": None}

        old_run_code = targetimageloadingsmalltalk._run_code
        def new_run_code(interp, code, as_benchmark=False):
            info["interpreter"] = interp
            return old_run_code(interp, code, as_benchmark=as_benchmark, raise_selector=True)
        targetimageloadingsmalltalk._run_code = new_run_code

        try:
            targetimageloadingsmalltalk.entry_point(
                [str(tmpdir), "-r", code, BenchmarkImage]
            )
        except targetimageloadingsmalltalk.SelectorNotification as e:
            info["selector"] = e.selector

        interp = info["interpreter"]
        selector = info["selector"]
        def interpret():
            return interp.perform(interp.space.wrap_int(0), selector)

        # XXX custom fishing, depends on the exact env var and format
        logfile = tmpdir.join("x.pypylog")
        os.environ['PYPYLOG'] = "jit-log-opt:%s" % logfile
        self.meta_interp(interpret, [], listcomp=True, listops=True, backendopt=True, inline=True)

        from rpython.jit.metainterp.warmspot import get_stats
        import re
        loops = get_stats().get_all_loops()
        logstr = "[bed8a96917a] {jit-log-opt-loop\n"
        logstr += "# Loop 0 (exp: eval) : entry bridge with %d ops\n" % len(loops[len(loops) -1].operations)
        logstr += "[p0, p1]\n"
        counter = 1
        for op in loops[len(loops) -1].operations:
            counter += 1
            op = str(op)
            match = re.match("[a-zA-Z0-9]+\.[a-zA-Z0-9]+:\d+", op)
            if match:
                op = op[0:match.span()[1]].strip()
            if op.startswith("i"):
                op = "+%d: %s" % (counter, op)
            logstr += op
            logstr += "\n"
        logfile.write(logstr + "[bed8a999a87] jit-log-opt-loop}\n")

        import pdb; pdb.set_trace()
        data = logparser.parse_log_file(str(tmpdir.join("x.pypylog")), verbose=False)
        data = logparser.extract_category(data, "jit-log-opt-")

        storage = LoopStorage()
        traces = [SimpleParser.parse_from_input(t) for t in data]
        main_loops = storage.reconnect_loops(traces)
        traces_w = []
        for trace in traces:
            if trace in main_loops:
                traces_w.append(Trace(trace))
            else:
                traces_w[len(traces_w) - 1].addbridge(trace)
        return traces_w

    def assert_matches(self, trace, expected):
        expected_lines = [
            line.strip()
            for line in expected.splitlines()
            if line and not line.isspace()
        ]
        parser = Parser(None, None, {}, "lltype", None, invent_fail_descr=None, nonstrict=True)
        expected_ops = [parser.parse_next_op(l) for l in expected_lines]
        aliases = {}
        assert len(trace) == len(expected_ops)
        for op, expected in zip(trace, expected_ops):
            self._assert_ops_equal(aliases, op, expected)

    def _assert_ops_equal(self, aliases, op, expected):
        assert op.name == expected.name
        assert len(op.args) == len(expected.args)
        for arg, expected_arg in zip(op.args, expected.args):
            if arg in aliases:
                arg = aliases[arg]
            elif arg != expected_arg and expected_arg not in aliases.viewvalues():
                aliases[arg] = arg = expected_arg
            assert arg == expected_arg


class Parser(oparser.OpParser):
    def get_descr(self, poss_descr, allow_invent):
        if poss_descr.startswith(("TargetToken", "<Guard")):
            return poss_descr
        return super(Parser, self).get_descr(poss_descr, allow_invent)

    def getvar(self, arg):
        return arg

    def create_op(self, opnum, args, res, descr):
        return Op(opname[opnum].lower(), args, res, descr)


class Trace(object):
    def __init__(self, trace):
        self._trace = trace
        self._bridges = []
        self._bridgeops = None
        self._loop = None

    def addbridge(self, trace):
        self._bridges.append(trace)

    @property
    def bridges(self):
        if self._bridgeops:
            return self._bridgeops
        else:
            self._bridgeops = []
            for bridge in self._bridges:
                self._bridgeops.append([op for op in bridge.operations if not op.name.startswith("debug_")])
            return self._bridgeops

    @property
    def loop(self):
        if self._loop:
            return self._loop
        else:
            self._loop = self._parse_loop_from(self._trace)
            return self._loop

    def _parse_loop_from(self, trace, label_seen=None):
        _loop = []
        for idx, op in enumerate(self._trace.operations):
            if label_seen and not op.name.startswith("debug_"):
                _loop.append(op)
            if op.name == "label":
                if label_seen is None: # first label
                    label_seen = False
                else:
                    label_seen = True # second label
        if len(_loop) == 0:
            raise ValueError("Loop body couldn't be found")
        return _loop
