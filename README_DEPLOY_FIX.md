# ProjectReady AI dependency conflict fix

This patch fixes Render `ResolutionImpossible` build failures by replacing the requirements file with a smaller, compatible set of top-level dependencies.

## Replace
- `requirements.txt`
- `.python-version`
- `runtime.txt`

Optional file:
- `constraints.txt`

## Render settings
Build command:

```bash
python -m pip install --upgrade pip setuptools wheel && pip install -r requirements.txt
```

If Render still reports dependency conflicts, use:

```bash
python -m pip install --upgrade pip setuptools wheel && pip install -r requirements.txt -c constraints.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Environment variable:

```text
PYTHON_VERSION=3.12.8
```

Then run: Manual Deploy -> Clear build cache & deploy.
