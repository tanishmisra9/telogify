import numpy as np
from psycopg2.extensions import adapt

import telogify.db  # noqa: F401  (import registers the numpy adapters)


def test_numpy_scalars_render_as_native_numbers():
    assert adapt(np.float64(330.5)).getquoted() == b"330.5"
    assert adapt(np.int64(7)).getquoted() == b"7"
