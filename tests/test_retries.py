from datetime import timedelta

import pytest

from gazette.retries import MAX_RETRIES, delay_after_failure


def test_three_immediate_retries_then_eight_half_hour_retries():
    delays = [delay_after_failure(attempt) for attempt in range(1, MAX_RETRIES + 1)]
    assert delays == [timedelta(0)] * 3 + [timedelta(minutes=30)] * 8
    assert sum(delays, timedelta()) == timedelta(hours=4)
    assert MAX_RETRIES + 1 == 12


@pytest.mark.parametrize("attempt", [0, 12])
def test_no_retry_before_first_attempt_or_after_final_attempt(attempt):
    with pytest.raises(ValueError, match="Aucune reprise"):
        delay_after_failure(attempt)
