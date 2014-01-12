import py


def pytest_addoption(parser):
    group = parser.getgroup("SPy JIT tests")
    group.addoption(
        "--spy",
        dest="spy",
        default=None,
        help="Path to a compiled SPy binary"
    )


def pytest_funcarg__spy(request):
    if request.config.getvalue("spy"):
        return str(py.path.local(request.config.getvalueorskip("spy")))
    else:
        return None
