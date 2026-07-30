.PHONY: verify test install

install:
	python -m pip install -e .

verify:
	python scripts/verify_run.py --check-environment
	python scripts/verify_run.py --check-repository

test:
	pytest -q
