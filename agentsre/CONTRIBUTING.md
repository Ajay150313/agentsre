# Contributing to agentsre

We love contributions! Here's how to get started.

## Getting Started

1. Fork the repo
2. Clone: `git clone https://github.com/YOUR_USERNAME/agentsre.git`
3. Install dev dependencies: `pip install -e .[dev]`
4. Create a branch: `git checkout -b feature/your-feature`
5. Make changes and test: `pytest tests/`
6. Commit: `git commit -m "feat: Your feature"`
7. Push: `git push origin feature/your-feature`
8. Open a PR

## Code Style

- Use type hints: `def function(param: str) -> int:`
- Write docstrings for all public functions
- 88-character line limit
- Run black: `black agentsre/`
- Run isort: `isort agentsre/`

## Testing

```bash
# Run tests
pytest tests/ -v

# Run coverage
pytest tests/ --cov=agentsre
```

## Areas We Need Help

- GCP/Azure implementations
- LangChain/CrewAI integrations
- More test coverage
- Documentation improvements

---

Created with ❤️ by Ajay Devineni
