"""Phase-1 tests: hashing."""

from __future__ import annotations

from raven_mcs.utils.hashing import (
    config_hash,
    environment_fingerprint,
    environment_hash,
    run_hash,
    sha256_json,
    sha256_text,
)


def test_sha256_text_stable() -> None:
    assert sha256_text("raven") == sha256_text("raven")
    assert sha256_text("a") != sha256_text("b")


def test_config_hash_key_order_invariant() -> None:
    a = {"seed": 1, "dataset": "x"}
    b = {"dataset": "x", "seed": 1}
    assert config_hash(a) == config_hash(b)


def test_environment_hash_nonzero() -> None:
    h = environment_hash()
    assert isinstance(h, str) and len(h) == 64


def test_sha256_json_nested() -> None:
    assert sha256_json({"a": [1, 2]}) == sha256_json({"a": [1, 2]})


def test_environment_fingerprint_includes_packages() -> None:
    packages = environment_fingerprint()["packages"]
    assert packages
    assert all("name" in item and "version" in item for item in packages)


def test_run_hash_is_stable_and_input_sensitive() -> None:
    values = {
        "config_hash_value": "a" * 64,
        "data_hash": "b" * 64,
        "event_trace_hash": "c" * 64,
        "environment_hash_value": "d" * 64,
        "git_commit": "NO_GIT",
        "git_state_hash": "e" * 64,
        "seed": 26001,
    }
    first = run_hash(**values)
    assert first == run_hash(**values)
    assert first != run_hash(**(values | {"seed": 26002}))
