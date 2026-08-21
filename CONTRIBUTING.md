## 📁 Файл №19: `/CONTRIBUTING.md`

Этот файл содержит **руководство для контрибьюторов** – разработчиков, которые хотят внести свой вклад в проект. Он описывает процессы разработки, стиль кода, тестирование и процедуру отправки Pull Request.

```markdown
# Contributing to TurboLLM

🎉 First off, thanks for taking the time to contribute! 🎉

The following is a set of guidelines for contributing to TurboLLM. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

---

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Your First Code Contribution](#your-first-code-contribution)
  - [Pull Requests](#pull-requests)
- [Development Setup](#development-setup)
- [Style Guides](#style-guides)
  - [Python Style Guide](#python-style-guide)
  - [Commit Messages](#commit-messages)
- [Testing](#testing)
- [Documentation](#documentation)
- [Getting Help](#getting-help)

---

## 📜 Code of Conduct

This project and everyone participating in it is governed by the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to [project maintainers](mailto:maintainers@turbollm.ai).

---

## 🤝 How Can I Contribute?

### Reporting Bugs

If you find a bug, please open an issue on GitHub with the following information:

- **Description** – what happened and what you expected to happen.
- **Steps to Reproduce** – provide a minimal code example or commands.
- **Environment** – OS, GPU, CUDA version, Python version, commit hash.
- **Logs** – relevant error messages or stack traces (use `[code]` blocks).

### Suggesting Enhancements

We welcome feature requests! Please describe:

- **Use case** – what problem does it solve?
- **Proposed solution** – how you imagine it working.
- **Alternatives** – any other approaches you've considered.

### Your First Code Contribution

Look for issues tagged with `good first issue` or `help wanted`. These are great starting points.

1. Fork the repository.
2. Create a new branch: `git checkout -b feature/your-feature-name`.
3. Make your changes.
4. Run tests and linters (see below).
5. Push and open a Pull Request.

### Pull Requests

- Make sure your PR targets the `main` branch.
- Include a clear description of what the PR does and why.
- Reference any related issues (e.g., `Closes #123`).
- Ensure all tests pass and code coverage does not decrease.
- Keep PRs focused – one feature/fix per PR.
- Update documentation if needed (README, CHANGELOG, docstrings).

---

## 🛠️ Development Setup

For local development:

```bash
# Clone the repo
git clone https://github.com/karamik/TurboLLM.git
cd TurboLLM

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dev dependencies
make dev-install

# Set up pre-commit hooks (optional but recommended)
pip install pre-commit
pre-commit install
```

---

## 📐 Style Guides

### Python Style Guide

We follow **PEP 8** with the following specifics:

- Use **Black** for code formatting (line length = 88).
- Use **Flake8** for linting (ignore E203, W503).
- Use **mypy** for type hints – all new code should have type annotations.

You can run formatters and linters with:

```bash
make format   # runs black
make lint     # runs flake8 & mypy
```

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat` – new feature
- `fix` – bug fix
- `docs` – documentation changes
- `style` – code style (formatting, missing semicolons, etc.)
- `refactor` – code restructuring
- `perf` – performance improvement
- `test` – adding/updating tests
- `chore` – maintenance (dependencies, configs)

**Example:**
```
feat(engine): add FP8 support for KV cache

- Enable FP8 quantization for key-value cache
- Reduce memory usage by ~40% for long contexts
- Add environment variable KV_CACHE_DTYPE

Closes #42
```

---

## 🧪 Testing

We use **pytest** for unit and integration tests.

```bash
# Run all tests
make test

# Run specific test file
pytest tests/test_serve.py -v

# Run with coverage
pytest --cov=turbollm tests/
```

**Test requirements:**
- All new features should include tests.
- Critical bug fixes should include a regression test.
- We aim for >80% code coverage.

---

## 📚 Documentation

- **README.md** – high-level overview and quick start.
- **CONTRIBUTING.md** – this file.
- **CHANGELOG.md** – version history.
- **Docstrings** – all public functions/classes should have Google-style docstrings.
- **Wiki** – detailed guides (deployment, tuning, enterprise modules).

---

## 📬 Getting Help

If you have questions, reach out via:

- **GitHub Issues** – for bug reports and feature requests.
- **Telegram**: [@tec_support_bot](https://t.me/tec_support_bot) – for general support and discussions.

We appreciate your contributions and look forward to building TurboLLM together! 🚀
```

