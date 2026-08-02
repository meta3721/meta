from __future__ import annotations

import inspect

import numpy as np

from raven_mcs.experiments.e1_entry import attempt_semantics
from raven_mcs.training.window_runner import FullWindowRunner


def test_attempt_set_defined_by_nonempty_observation_buffer() -> None:
    assert attempt_semantics(1, 0)["attempted"] == 1
    assert attempt_semantics(0, 1)["attempted"] == 0


def test_attempt_set_frozen_before_U() -> None:
    assert attempt_semantics(2, 0)["attempted"] == attempt_semantics(2, 1)["attempted"]


def test_usable_implies_attempted() -> None:
    for observed in (0, 1):
        for u_value in (0, 1):
            row = attempt_semantics(observed, u_value)
            assert not row["usable"] or row["attempted"]


def test_A_subset_E() -> None:
    rows = [attempt_semantics(n, u) for n, u in [(0, 1), (2, 0), (3, 1)]]
    assert all(not row["usable"] or row["attempted"] for row in rows)


def test_nonattempt_client_never_trains() -> None:
    source = inspect.getsource(FullWindowRunner._update_lagged_estimators)
    assert "if included:" in source


def test_nonattempt_client_never_aggregates() -> None:
    source = inspect.getsource(FullWindowRunner._process_window)
    assert "set(e_r_clients) != set(attempted_clients)" in source


def test_attempted_field_persisted() -> None:
    row = attempt_semantics(3, 1)
    assert set(row) == {"attempted", "usable", "attempt_failure", "non_attempt"}


def _fixture() -> list[dict[str, int | str]]:
    return [
        {"client": "A", "observed": 3, "U": 1},
        {"client": "B", "observed": 2, "U": 0},
        {"client": "C", "observed": 0, "U": 0},
    ]


def _included() -> list[dict[str, int | str]]:
    return [
        row for row in _fixture()
        if attempt_semantics(int(row["observed"]), int(row["U"]))["attempted"]
    ]


def test_q_history_only_contains_attempt_set() -> None:
    assert {row["client"] for row in _included()} == {"A", "B"}


def test_q_history_retains_failed_attempts() -> None:
    assert any(row["client"] == "B" and row["U"] == 0 for row in _included())


def test_q_history_excludes_nonattempts() -> None:
    assert all(row["client"] != "C" for row in _included())


def test_q_training_rows_equal_attempt_count() -> None:
    assert len(_included()) == sum(
        attempt_semantics(int(row["observed"]), int(row["U"]))["attempted"]
        for row in _fixture()
    )


def test_q_failed_attempt_fixture() -> None:
    assert [row["client"] for row in _included()] == ["A", "B"]


def test_q_current_window_added_after_close() -> None:
    source = inspect.getsource(FullWindowRunner._process_window)
    assert source.index("skip_empty_window") < source.index(
        "self._update_lagged_estimators", source.index("skip_empty_window")
    )
    assert source.rindex("apply_server_update") < source.rindex(
        "self._update_lagged_estimators"
    )


def test_q_current_U_not_predict_itself() -> None:
    source = inspect.getsource(FullWindowRunner._update_lagged_estimators)
    assert source.index("q_hat =") < source.index("update_lagged(")


def test_q_history_contains_success_and_failure_when_available() -> None:
    assert {int(row["U"]) for row in _included()} == {0, 1}
