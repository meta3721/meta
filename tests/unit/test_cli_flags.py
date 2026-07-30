"""Phase-1 tests: common CLI flags exist."""

from __future__ import annotations

from raven_mcs.utils.cli import build_common_parser


def test_common_flags_present() -> None:
    parser = build_common_parser("test")
    args = parser.parse_args(
        [
            "--dry-run",
            "--resume",
            "--max-workers",
            "4",
            "--fail-fast",
            "--device",
            "cpu",
            "--seed",
            "26001",
            "--output-dir",
            "outputs/runs",
        ]
    )
    assert args.dry_run is True
    assert args.resume is True
    assert args.max_workers == 4
    assert args.fail_fast is True
    assert args.device == "cpu"
    assert args.seed == 26001
    assert str(args.output_dir).replace("\\", "/").endswith("outputs/runs")
