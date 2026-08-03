"""Integration checks for E1-R2 SEALED gate self-containment prerequisites."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


REQUIRED_SCRIPTS = [
    "scripts/check_e1_r2_results_seal_gates.py",
    "scripts/check_e1_formal_gates.py",
    "scripts/statistical_tests.py",
]


def test_seal_gate_scripts_exist() -> None:
    for rel in REQUIRED_SCRIPTS:
        assert (ROOT / rel).is_file(), rel


def test_sealed_gate_evaluation_imports_without_src_package() -> None:
    # Importing the no-harm helper must not require raven_mcs source package.
    from check_e1_formal_gates import _no_harm_gate_ok

    assert callable(_no_harm_gate_ok)


@pytest.mark.skipif(
    not (ROOT / "outputs/statistics/E1_R2_FINAL_SEALED/holm_results.csv").is_file(),
    reason="FINAL_SEALED stats not generated yet",
)
def test_final_sealed_holm_families() -> None:
    import pandas as pd

    holm = pd.read_csv(ROOT / "outputs/statistics/E1_R2_FINAL_SEALED/holm_results.csv")
    assert set(holm["family_size"].astype(int)) == {4}
    assert holm.groupby("family_id").ngroups == 5
