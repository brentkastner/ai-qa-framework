# GitHub Repository Settings Checklist

Follow this checklist after pushing to configure your GitHub repository for open source.

## Repository Settings (Settings > General)

- [ ] **Description:** "Autonomous AI-driven QA framework — give it a URL, get comprehensive test coverage"
- [ ] **Website:** `https://github.com/brentkastner/ai-qa-framework#readme`
- [ ] **Topics:** `qa`, `testing`, `ai`, `automation`, `playwright`, `python`, `anthropic`, `claude`
- [ ] **Set visibility to Public**

### Features

- [ ] Enable **Issues**
- [ ] Enable **Discussions** (for community Q&A)
- [ ] Disable **Wiki** (documentation lives in the repo)
- [ ] Enable **"Automatically delete head branches"** after PR merge
- [ ] Enable **Sponsorship** (optional — if you want to accept funding)

## Branch Protection (Settings > Branches)

Add a branch protection rule for `main`:

- [ ] **Require a pull request before merging**
  - Require 1 approval
- [ ] **Require status checks to pass before merging**
  - Add the `test` check from the CI workflow
  - Require branches to be up to date before merging
- [ ] **Do not allow force pushes**
- [ ] **Do not allow deletions**

## Security (Settings > Code security and analysis)

- [ ] Enable **Dependabot alerts**
- [ ] Enable **Dependabot security updates**
- [ ] Enable **Secret scanning**
- [ ] Enable **Push protection** (prevents accidental secret commits)
- [ ] Enable **Private vulnerability reporting** (for SECURITY.md workflow)

## Actions (Settings > Actions > General)

- [ ] Allow actions from this repository and select non-fork organizations
- [ ] Set workflow permissions to **"Read repository contents"** (least privilege)

## Optional

- [ ] Add a **CODEOWNERS** file if you want automatic review assignment
- [ ] Set up **GitHub Pages** if you want to host documentation
- [ ] Configure **Environments** for staging/production deployments
