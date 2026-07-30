"""Hard-gate registry stubs (implemented in later phases / E0)."""

from __future__ import annotations

from enum import Enum


class HardGate(str, Enum):
    G0_DATA = "G0"
    G1_EVENT = "G1"
    G2_TIMING = "G2"
    G3_WEIGHTS = "G3"
    G4_P2 = "G4"
    G5_DEBT = "G5"
    G6_BALANCED = "G6"
    G7_ORACLE = "G7"


GATE_STATUS_PENDING = "PENDING"
GATE_STATUS_PASS = "PASS"
GATE_STATUS_FAIL = "FAIL"
GATE_STATUS_NA = "N/A"
