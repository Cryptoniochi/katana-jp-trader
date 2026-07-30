# Dependency unification

Project KATANA now manages runtime and development dependencies through
`pyproject.toml`.

## Install runtime dependencies

```powershell
python -m pip install -e .
```

## Install runtime and development dependencies

```powershell
python -m pip install -e ".[dev]"
```

## Sprint89-1B cleanup

After replacing `pyproject.toml` and successfully running the install command,
the following temporary file is no longer required:

```text
requirements_sprint89_1b.txt
```

`README_SPRINT89_1B.md` may remain under `docs/` as development history.
