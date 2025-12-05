# Contributing Guide

## Branches

```
main                    ← Stable releases only (protected)
  │
  └── dev               ← All development happens here (protected)
        │
        ├── feature/INF-100-udp-listener
        ├── feature/INF-103-packet-parser
        └── feature/INF-107-motion-algorithm
```

## Workflow

### 1. Start a Feature

```bash
git checkout dev
git pull origin dev
git checkout -b feature/INF-XXX-short-description
```

### 2. Do Your Work

- Implement the ticket
- Write/update tests
- Commit often with clear messages

```bash
git add .
git commit -m "INF-XXX: Brief description of change"
```

### 3. Push and Create PR

```bash
git push -u origin feature/INF-XXX-short-description
```

Then on GitHub:
1. Create Pull Request → **base: dev** ← compare: your branch
2. Fill in the PR template
3. Request review from **at least 1 teammate**

### 4. Review Rules

- **1 approval required** before merging
- Reviewer checks:
  - Code works (tests pass)
  - Code makes sense
  - No obvious bugs
- After approval → **Squash and merge** to dev

### 5. Cleanup

```bash
git checkout dev
git pull origin dev
git branch -d feature/INF-XXX-short-description
```

---

## Important: The Skeleton is NOT Sacred

The existing code structure is a **starting point**, not a contract.

**You CAN and SHOULD:**
- Rewrite entire files if needed
- Change function signatures
- Add/remove classes
- Restructure modules
- Ignore the TODOs if you have a better approach

**Just make sure:**
- The overall data flow works (UDP → Parse → Algorithm → Driver)
- Tests pass
- You document what you changed in the PR

---

## Commit Message Format

```
INF-XXX: Short description (max 50 chars)

Optional longer explanation if needed.
- Bullet points are fine
- Explain WHY, not just WHAT
```

**Examples:**
```
INF-103: Implement packet header parsing
INF-107: Rewrite algorithm to fix circular import
INF-100: Add timeout handling to UDP socket
```

---

## Quick Commands

```bash
# See what branch you're on
git branch

# See all branches
git branch -a

# Switch to dev
git checkout dev

# Update your branch with latest dev
git checkout your-branch
git merge dev

# Undo last commit (keep changes)
git reset --soft HEAD~1
```
