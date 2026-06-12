# Releasing Sifty

Sifty ships two artifacts per release, both automated by
[`.github/workflows/release.yml`](../.github/workflows/release.yml):

1. **PyPI package** (`pip install sifty`) — built and uploaded via PyPI
   **Trusted Publishing** (OIDC), so no API token is ever stored in the repo.
2. **`sifty.exe`** — a standalone Windows executable attached to the GitHub
   Release (no Python needed to run it).

## One-time setup (do this once)

### 1. Create a PyPI account

Sign up at <https://pypi.org/account/register/>. The project name `sifty` is
currently unclaimed; the first successful publish claims it.

### 2. Register the GitHub repo as a Trusted Publisher

Because the project doesn't exist on PyPI yet, add a **pending** publisher:

1. Go to <https://pypi.org/manage/account/publishing/>.
2. Under "Add a new pending publisher", fill in:
   - **PyPI Project Name:** `sifty`
   - **Owner:** `Vortrix5`
   - **Repository name:** `sifty`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
3. Save.

### 3. (Recommended) Add a GitHub environment named `pypi`

In the GitHub repo: **Settings → Environments → New environment → `pypi`**.
You can add a required-reviewer protection rule here so a human approves each
publish. The workflow's `environment: pypi` already points at it.

## Cutting a release

1. Bump the version in **two** places and update the changelog:
   - `src/sifty/__init__.py` → `__version__`
   - `pyproject.toml` → `version`
   - add a section to `CHANGELOG.md`
2. Commit, then tag and push:
   ```powershell
   git tag v0.6.1
   git push origin main --tags
   ```
3. On GitHub: **Releases → Draft a new release**, choose the tag (e.g.
   `v0.6.1`), paste the changelog section as the notes, and **Publish**.
4. Publishing the release triggers `release.yml`, which:
   - builds the wheel + sdist and uploads them to PyPI, and
   - builds `sifty.exe` and attaches it to the release.

## Verifying a release

```powershell
pip install --upgrade sifty
sifty version          # should match the tag
```

The exe appears under the release's "Assets". `sifty selfupdate` compares the
installed version against PyPI and upgrades via pipx.

## Manual build (local, for testing)

```powershell
.\.venv\Scripts\python.exe -m pip install build
.\.venv\Scripts\python.exe -m build          # -> dist/*.whl, *.tar.gz
.\.venv\Scripts\python.exe -m twine check dist/*
```

For a local exe build, run the `/package-exe` workflow (PyInstaller).
