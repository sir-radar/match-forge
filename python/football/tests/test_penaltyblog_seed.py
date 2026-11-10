import threading

import numpy as np
from football.forecasting import penaltyblog_models


def test_seeded_numpy_sections_do_not_interleave_across_threads() -> None:
    with penaltyblog_models._numpy_seed(7):
        expected = (np.random.random(), np.random.random())

    entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()
    draws: list[float] = []

    def first() -> None:
        with penaltyblog_models._numpy_seed(7):
            draws.append(np.random.random())
            entered.set()
            release.wait(timeout=5)
            draws.append(np.random.random())

    def second() -> None:
        with penaltyblog_models._numpy_seed(99):
            second_entered.set()
            np.random.random()

    one = threading.Thread(target=first)
    two = threading.Thread(target=second)
    one.start()
    assert entered.wait(timeout=5)
    two.start()
    assert not second_entered.wait(timeout=0.2)
    release.set()
    one.join(timeout=5)
    two.join(timeout=5)

    assert second_entered.is_set()
    assert tuple(draws) == expected
