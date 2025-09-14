import numba
from functools import wraps

# Keep a reference to the original jit decorator
original_jit = numba.jit

@wraps(original_jit)
def jit_wrapper(*args, **kwargs):
    """
    A wrapper for numba.jit that disables caching.
    This is a workaround for a bug where numba's caching mechanism fails
    in some containerized environments like Celery, raising a RuntimeError.
    By forcing cache=False, we prevent the error.
    """
    kwargs['cache'] = False
    return original_jit(*args, **kwargs)

# Monkey-patch numba.jit to use our wrapper
numba.jit = jit_wrapper

# Also patch njit if it's used
if hasattr(numba, 'njit'):
    original_njit = numba.njit

    @wraps(original_njit)
    def njit_wrapper(*args, **kwargs):
        kwargs['cache'] = False
        return original_njit(*args, **kwargs)

    numba.njit = njit_wrapper
