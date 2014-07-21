
from rpython.rlib import rgc, objectmodel, jit

# ======== Internal functions ========

def flag(gcref):
    return rgc.get_gcflag_extra(gcref)

def toggle_flag(gcref):
    rgc.toggle_gcflag_extra(gcref)

def references(gcref):
    return rgc.get_rpy_referents(gcref)

def gc_roots():
    return rgc.get_rpy_roots()

def _clear_all_flags(gcrefs):
    for gcref in gcrefs:
        if gcref and flag(gcref):
            toggle_flag(gcref)
            _clear_all_flags(references(gcref))

def _walk_gc_references(func, extra_parameter, collect_into, gcrefs):
    for gcref in gcrefs:
        if gcref and not flag(gcref):
            toggle_flag(gcref)
            result = func(gcref, extra_parameter)
            if result is not None:
                collect_into.append(result)
            _walk_gc_references(func, extra_parameter, collect_into, references(gcref))
    return collect_into

# ======== API of this module ========
# The extra_parameter is here to avoid creating closures in the function parameters,
# and still be able to pass some context into the functions. It should always be a short tuple,
# so that rpython can autmatically specialize these functions. If it fails to do so, annotate
# all functions with extra_parameter with @objectmodel.specialize.argtype(2).

def try_cast(type, gcref):
    return rgc.try_cast_gcref_to_instance(type, gcref)

@jit.dont_look_inside
def walk_gc_references(func, extra_parameter = None):
    roots = gc_roots()
    result = _walk_gc_references(func, extra_parameter, [], roots)
    _clear_all_flags(roots)
    _clear_all_flags(gc_roots()) # Just in case
    return result

def walk_gc_references_of_type(type, func, extra_parameter = None):
    def check_type(gcref, extra):
        type, func, extra_parameter = extra
        w_obj = try_cast(type, gcref)
        if w_obj:
            func(w_obj, extra_parameter)
        return None
    walk_gc_references(check_type, (type, func, extra_parameter))

def collect_gc_references_of_type(type, filter_func = lambda obj, extra: True, extra_parameter = None):
    def check_type(gcref, extra):
        type, filter_func, extra_parameter = extra
        w_obj = try_cast(type, gcref)
        if w_obj and filter_func(w_obj, extra_parameter):
            return w_obj
        return None
    return walk_gc_references(check_type, (type, filter_func, extra_parameter))
