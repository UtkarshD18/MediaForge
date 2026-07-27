# Release Checklist - MediaForge V1 (v0.1.0-rc1)

This checklist tracks the release preparation verification steps required to promote **MediaForge** to Release Candidate 1.

---

## ✅ Definition of Done (DoD) Checks

### 1. Code Health
- [x] Ruff lint checks pass without errors (`ruff check .`).
- [x] Ruff format audits pass check limits (`ruff format --check .`).
- [x] Mypy typing checks verify type correctness (`mypy src/`).
- [x] Bandit scans report 0 high/medium severity findings.

### 2. Verification Suites
- [x] Hardware CUDA transcode executes and writes fallback logs.
- [x] Duplicate detection bypass validates hash skip metrics.
- [x] SQLite WAL database survives daemon crashes.
- [x] Ingestion stress test (100 simultaneous drops) completes.
- [x] Media matrix check ingests all formats.
- [x] Directory recreation routines verify path resilience.
- [x] Performance profile benchmarks match target budgets.

### 3. Packaging & Assets
- [x] `LICENSE` (MIT) present at project root.
- [x] `CHANGELOG.md` updated with release definitions.
- [x] `CONTRIBUTING.md` outlines styling and PR flows.
- [x] `SECURITY.md` documents reporting emails.
- [x] `CODE_OF_CONDUCT.md` establishes community rules.
- [x] `pyproject.toml` lists dependencies and scripts entry points.
- [x] `.gitignore` blocks local database files, logs, and venvs.

---

## 🚀 Release Promotion Instructions

Execute the local tagging and distribution setup:

1. **Verify all tests pass**:
   ```bash
   python -m unittest discover -s tests/
   ```

2. **Commit packaging files**:
   ```bash
   git add LICENSE CHANGELOG.md CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md pyproject.toml .gitignore
   git commit -m "chore: release configuration packaging for v0.1.0-rc1"
   ```

3. **Tag the release candidate locally**:
   ```bash
   git tag -a v0.1.0-rc1 -m "Release Candidate 1: Ingestion engine and verification suites complete."
   ```
   *(Note: Do not push to origin until explicitly requested.)*
