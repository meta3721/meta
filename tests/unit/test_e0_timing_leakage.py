"""E0.5 window timing and E0.6 static q-feature leakage scan."""

from __future__ import annotations

import pytest

from raven_mcs.propensity.leakage import (
    FORBIDDEN_Q_FEATURE_TOKENS,
    assert_q_features_leakage_free,
    scan_q_feature_names,
)
from raven_mcs.training.window_timing import WindowClock, WindowTimingError


def test_e0_5_window_model_frozen_and_single_update() -> None:
    clock = WindowClock(num_windows=3)
    assert clock.model_version == 0
    clock.register_local_work(downloaded_version=0)
    clock.register_local_work(downloaded_version=0)
    version = clock.apply_server_update()
    assert version == 1
    assert clock.current_window == 1

    # Historical checkpoints are legitimate stale downloads.
    clock.register_local_work(downloaded_version=0)
    clock.register_local_work(downloaded_version=1)
    with pytest.raises(WindowTimingError, match="future downloads"):
        clock.register_local_work(downloaded_version=2)
    clock.apply_server_update()
    assert clock.model_version == 2

    # Empty window publishes an unchanged checkpoint under the next version.
    before = clock.model_version
    clock.skip_empty_window()
    assert clock.model_version == before + 1
    assert clock.current_window == 3


def test_e0_5_rejects_second_update_in_same_window() -> None:
    clock = WindowClock(num_windows=1)
    # Force the internal guard by simulating a stuck half-update.
    clock.updates_in_window = 1
    with pytest.raises(WindowTimingError, match="only one global update"):
        clock.apply_server_update()


def test_e0_6_forbids_post_outcome_q_features() -> None:
    assert set(FORBIDDEN_Q_FEATURE_TOKENS) >= {
        "realized",
        "arrival",
        "future",
        "update_norm",
        "update_value",
        "actual_delay",
    }
    allowed = ["device_class", "network_budget", "model_age_bucket", "deadline_slack"]
    assert scan_q_feature_names(allowed) == []
    assert_q_features_leakage_free(allowed)

    banned = ["hist_load", "actual_delay", "pre_arrival_ok", "update_norm_lag"]
    hits = scan_q_feature_names(banned)
    assert "actual_delay" in hits
    assert "update_norm_lag" in hits
    with pytest.raises(ValueError, match="Forbidden"):
        assert_q_features_leakage_free(banned)
