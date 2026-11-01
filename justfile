# Marketing-Bot (Custom ArtBOT) quality gates and daily roundup commands.
# Aligns with STANDARDS.md: format check, lint, strict typecheck, shac test/check,
# and deterministic pytest run twice in random order with 100% line & branch coverage.

set shell := ["bash", "-uc"]

# Run full quality gate: format check, lint, typecheck, shac test & check, and 2x randomized 100%-coverage pytest
check: fmt-check lint typecheck shac-test shac-check test
	@echo "All quality gates passed!"

# Format all files via shac and ruff
fmt:
	ruff format .
	shac fmt

# Check Python formatting
fmt-check:
	ruff format --check .

# Lint Python code
lint:
	ruff check .

# Fix auto-fixable lint issues
lint-fix:
	ruff check --fix .

# Strict typechecking
typecheck:
	mypy --strict src tests

# Run Starlark unit tests for shac policy and API contract rules
shac-test:
	shac test

# Run shac policy, API contract, lint, and format checks across all tracked files
shac-check:
	shac check --all

# Run test suite twice in random order enforcing 100% line and branch coverage (STANDARDS.md Section 1)
test:
	pytest
	pytest

# Generate daily roundup from live Agility PR MCP & Saved Topics
roundup date="":
	PYTHONPATH=src:../artbot/src python3 -m marketing_bot.cli generate-daily {{ if date != "" { "--date " + date } else { "" } }}

# Verify upstream ArtBOT tag and commit pin
upstream-status:
	PYTHONPATH=src:../artbot/src python3 -m marketing_bot.cli upstream-status
