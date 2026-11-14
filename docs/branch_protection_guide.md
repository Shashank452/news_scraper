# GitHub CI/CD & Branch Protection Guide

This repository is configured with automated GitHub Actions CI/CD to ensure that **code can only be merged into `main` if all test cases pass**.

---

## 1. How the CI/CD Pipeline Works

The GitHub Actions workflow is located at [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

### Trigger Events:
- **On Push**: Any branch (`feature/**`, `fix/**`, `develop`, etc.)
- **On Pull Request**: When targeting `main` or `master`

### Automated Checks:
1. **Multi-Version Test Matrix**: Executes the test suite on Python 3.10, 3.11, and 3.12.
2. **Dependency Resolution**: Tests clean installation from `requirements.txt`.
3. **Syntax Validation**: Compiles all core modules (`python -m py_compile ...`).
4. **Pytest Suite**: Executes all 38 unit & integration tests covering:
   - REST API endpoints and streaming/incremental sync
   - Multi-level deduplication and database retention purge
   - BSE, NSE, Media, and Regulatory Policy scrapers
   - News Aggregator orchestration
   - JSON & CSV exporters
   - Scheduler service and master runner
5. **Quality Gate (`Merge Protection Gate`)**: A final checkpoint job that confirms all matrix tests passed.

---

## 2. Enabling Branch Protection on GitHub (Enforcing Tests Before Merge)

To strictly prevent code from being merged into `main` when tests fail, configure GitHub Branch Protection:

1. Open your repository on GitHub.
2. Navigate to **Settings** > **Branches** (in the left sidebar).
3. Under **Branch protection rules**, click **Add branch protection rule** (or edit existing rule for `main`).
4. Set **Branch name pattern** to `main` (or `master`).
5. Enable the following settings:
   - [x] **Require a pull request before merging**
   - [x] **Require status checks to pass before merging**
     - [x] **Require branches to be up to date before merging**
     - In the search box, search for and select:
       - `Merge Protection Gate`
       - `Test Suite (Python 3.11)`
   - [x] **Do not allow bypassing the above settings** (enforces checks for administrators too)
6. Click **Save changes** at the bottom of the page.

---

## 3. Recommended Developer Workflow

### Step 1: Create a feature branch
```bash
git checkout -b feature/my-feature
```

### Step 2: Make changes & test locally before pushing
Run the automated pre-push verification script:
```powershell
python scripts/verify_all.py
```

### Step 3: Push feature branch to GitHub
```bash
git add .
git commit -m "feat: description of changes"
git push origin feature/my-feature
```

### Step 4: Open Pull Request
- Open a PR from `feature/my-feature` into `main`.
- GitHub Actions automatically triggers and runs all 38 test cases.
- **If any test fails**: The PR displays a red cross `❌` and the **"Merge pull request"** button is completely disabled.
- **If all tests pass**: The PR displays a green check `✅` and allows merging.
