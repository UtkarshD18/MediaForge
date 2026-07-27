# Contributing to MediaForge

We welcome contributions to MediaForge! To ensure code quality and maintainability, please adhere to the following developer guidelines.

---

## 🛠️ Local Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/username/mediaforge.git
   cd mediaforge
   ```

2. **Initialize python environment**:
   We recommend Astral's `uv` tool for fast package resolution:
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -r requirements.txt
   uv pip install ruff mypy bandit pytest pre-commit
   ```

3. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

---

## 📐 Styling and Coding Standards

We enforce strict formatting rules using **Ruff**:
* **Lints**: `ruff check .`
* **Format**: `ruff format --check .`
* **Types**: `mypy --ignore-missing-imports --explicit-package-bases src/`

Please make sure all checks pass locally before filing a Pull Request.

---

## 🧪 Testing Guidelines

Verify your work by running the full unit test discovery suite:
```bash
python -m unittest discover -s tests/
```
If implementing new features (e.g. metadata fields or compression profiles), write matching unit tests inside the `tests/` directory.

---

## 🌿 Pull Request Procedure

1. Create a descriptive branch from `develop` (e.g. `feature/vaapi-acceleration`).
2. Implement and test your modifications.
3. Verify formatting and security scans locally.
4. Commit using structured commit logs and file a PR against `develop`.
