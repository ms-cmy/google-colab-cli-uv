install_local:
	uv tool install --force --editable .

run_tests:
	uv run pytest tests/
