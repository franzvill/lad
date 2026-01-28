# Contributing to LAD-A2A

Thank you for your interest in contributing to LAD-A2A!

## Ways to Contribute

- **Spec feedback**: Open issues for clarifications or improvements
- **Reference implementations**: In other languages (TypeScript, Go, Rust)
- **Testing**: Additional conformance tests
- **Documentation**: Examples, tutorials, translations
- **Design partners**: Real-world deployment feedback

## Development Setup

```bash
# Clone the repo
git clone https://github.com/franzvill/lad.git
cd lad

# Set up Python environment
cd reference
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Ensure tests pass (`pytest tests/ -v`)
5. Submit a pull request

## Spec Changes

Changes to the protocol specification (`spec/spec.md`) require:

- Clear rationale in the PR description
- Consideration of backwards compatibility
- Updated JSON schemas if applicable
- Updated conformance tests
- Review by maintainers

## Code Style

- Python: Follow PEP 8
- Use type hints
- Add docstrings to public functions
- Keep dependencies minimal

## Testing

The test suite validates conformance with the spec:

```bash
cd reference
pytest tests/ -v
```

For network simulation testing:

```bash
cd reference/simulation
./run.sh
```

## Questions?

Open a GitHub Issue or Discussion.

## Code of Conduct

Be respectful, constructive, and inclusive. We welcome contributors of all backgrounds and experience levels.
