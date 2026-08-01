.PHONY: verify test install phase0-audit phase1-smoke phase2a-smoke phase2b-g0 e0 gates

install:
	python -m pip install -e .

verify:
	python scripts/verify_run.py --check-environment
	python scripts/verify_run.py --check-repository

test:
	pytest -q

phase0-audit:
	python scripts/audit_phase0.py --resume

phase1-smoke:
	python scripts/smoke_run_lifecycle.py --dry-run

phase2a-smoke:
	pytest -q tests/unit/test_data_cli.py

phase2b-g0:
	python scripts/check_g0_data.py --data-root data --output-dir docs/audits

e0:
	python scripts/check_e0.py --output-dir docs/audits

gates:
	python scripts/check_hard_gates.py --output-dir docs/audits
