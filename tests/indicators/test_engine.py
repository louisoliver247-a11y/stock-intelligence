from datetime import timedelta

import pytest

from analysis.indicators import IndicatorEngine, IndicatorInputError, calculate_series


@pytest.mark.parametrize('provider', ['sharekhan', 'hdfc_sky'])
def test_results_independent_of_provider(provider, observations, calendar, short_config):
    rows = observations([100 + i % 7 for i in range(30)])
    supplied = [row.model_copy(update={'candle': row.candle.model_copy(
        update={'provider': provider, 'source': provider + '_history'})}) for row in rows]
    expected = list(calculate_series(rows, calendar, as_of=rows[-1].known_at, config=short_config))
    actual = list(calculate_series(supplied, calendar, as_of=rows[-1].known_at, config=short_config))
    # Audit digests retain provenance, while every numerical output remains identical.
    assert [row.model_dump(exclude={'input_digest'}) for row in actual] == [
        row.model_dump(exclude={'input_digest'}) for row in expected]
    assert actual[-1].input_digest != expected[-1].input_digest


def test_prefix_invariance_and_incremental_equivalence(observations, calendar, short_config):
    rows = observations([100 + i % 7 for i in range(30)])
    full = list(calculate_series(rows, calendar, as_of=rows[-1].known_at, config=short_config))
    engine = IndicatorEngine(calendar, short_config)
    for index, row in enumerate(rows):
        assert engine.update(row, as_of=row.known_at) == full[index]
        prefix = list(calculate_series(rows[:index + 1], calendar, as_of=row.known_at, config=short_config))
        assert prefix == full[:index + 1]


@pytest.mark.parametrize("case,code", [
    ("partial", "UNVALIDATED_CANDLE"),
    ("flagged", "UNVALIDATED_CANDLE"),
    ("future", "NOT_YET_KNOWN"),
    ("mixed", "MIXED_STREAM"),
    ("gap", "MISSING_CANDLES"),
    ("correction", "CORRECTION_REQUIRES_REPLAY"),
    ("out_of_order", "OUT_OF_ORDER_CANDLE"),
])
def test_rejection_does_not_mutate_state(case, code, observations, calendar, short_config):
    rows = observations([100, 101, 102, 103])
    engine = IndicatorEngine(calendar, short_config)
    engine.update(rows[0], as_of=rows[-1].known_at)
    engine.update(rows[1], as_of=rows[-1].known_at)
    candidate, cutoff = rows[2], rows[-1].known_at
    if case in {"partial", "flagged", "mixed"}:
        updates = {"partial": {"is_complete": False},
                   "flagged": {"is_complete": False, "quality_flags": ("TEST",)},
                   "mixed": {"instrument_id": "another"}}[case]
        candidate = candidate.model_copy(update={"candle": candidate.candle.model_copy(update=updates)})
    elif case == "future":
        cutoff = candidate.known_at - timedelta(seconds=1)
    elif case == "gap":
        candidate = rows[3]
    elif case == "correction":
        candidate = rows[1].model_copy(update={"revision": 2})
    else:
        candidate = rows[0]
    before = engine.latest
    with pytest.raises(IndicatorInputError, match=code):
        engine.update(candidate, as_of=cutoff)
    assert engine.latest == before
    expected = list(calculate_series(rows, calendar, as_of=rows[-1].known_at, config=short_config))
    assert engine.update(rows[2], as_of=rows[-1].known_at) == expected[2]


def test_duplicate_is_idempotent(observations, calendar, short_config):
    row = observations([100])[0]
    engine = IndicatorEngine(calendar, short_config)
    first = engine.update(row, as_of=row.known_at)
    assert engine.update(row, as_of=row.known_at) == first
    assert engine.count == 1
