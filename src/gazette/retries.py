"""Delais de reprise communs au DAG et aux tests, sans dependance a Airflow."""

from datetime import timedelta

IMMEDIATE_RETRIES = 3
DELAYED_RETRIES = 8
MAX_RETRIES = IMMEDIATE_RETRIES + DELAYED_RETRIES
DELAYED_RETRY_DELAY = timedelta(minutes=30)


def delay_after_failure(try_number: int) -> timedelta:
    """Delai apres la tentative echouee, numerotee a partir de 1."""
    if not 1 <= try_number <= MAX_RETRIES:
        raise ValueError("Aucune reprise prevue apres cette tentative")
    if try_number <= IMMEDIATE_RETRIES:
        return timedelta(0)
    return DELAYED_RETRY_DELAY
