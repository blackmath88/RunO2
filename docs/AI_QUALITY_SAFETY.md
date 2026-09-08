# AI-assisted code quality & safety

runO2 was built quickly and with extensive help from ChatGPT, Claude, delta.dev and VS Code.

That is useful leverage, but it creates a second question alongside the data question:

> **How do I know the AI-generated code is any good?**

The answer here is deliberately not “ask another model”.

The project uses several independent lenses and publishes their limitations.

## The evaluation stack

| Layer | Tool / method | What it can tell us | What it cannot prove |
|---|---|---|---|
| behavioral correctness | `pytest` | known expected behavior still works | untested behavior is correct |
| senior/YAGNI review | repository `AGENTS.md`; optional Ponytail-style review | duplication, over-building, unnecessary dependencies, awkward abstractions | runtime correctness or security |
| code quality | Ruff | common mistakes, dead/unused patterns, consistency issues | architectural fitness |
| Python security patterns | Bandit | suspicious APIs and common insecure Python patterns | absence of exploitable vulnerabilities |
| static security / bug patterns | Semgrep CE | broader code patterns and security smells | complete data-flow proof |
| semantic security analysis | GitHub CodeQL | deeper cross-file/data-flow vulnerability classes | complete safety |
| Python dependency CVEs | `pip-audit` | dependencies with known advisories | unknown vulnerabilities or maintainer trust |
| Worker dependency CVEs | `npm audit` | registry advisories for Node dependencies | unknown vulnerabilities or provenance quality |
| dependency drift | Dependabot | outdated Python, npm, Docker and Actions dependencies | that the latest version is good or safe |
| human / model review | explicit review rubric | context, architecture, evidence boundaries | independence if the same assumptions are reused |

## Why multiple independent lenses?

AI code review has the same failure mode as AI code generation: a fluent explanation can still miss the bug.

So the process separates:

```text
model judgement
      ≠
static analysis
      ≠
known-vulnerability databases
      ≠
behavioral tests
      ≠
architectural judgement
```

Agreement raises confidence. Disagreement is useful: it tells us where to inspect manually.

## Baseline first, enforcement second

The first pass is intentionally an **evaluation baseline**.

- `pytest` is blocking.
- Ruff, Bandit, Semgrep and dependency audits report findings without automatically rejecting the build.
- CodeQL publishes findings to GitHub's security analysis.
- Dependabot watches dependency drift.

Why not make every scanner a hard gate immediately?

Because a mature codebase — especially one built quickly — can contain existing warnings and false positives. Turning on a scanner and then blindly editing until it is green can create more risk than it removes.

The intended sequence is:

```text
scan
→ classify findings
→ reproduce / verify
→ fix real issues
→ record accepted risk
→ only then promote high-signal checks to blocking gates
```

## Local VS Code workflow

The repository includes `.vscode/tasks.json`.

From VS Code:

1. open **Terminal → Run Task…**
2. choose **runO2: full local quality baseline**

Or run individual tasks:

- tests
- Ruff review
- Bandit security
- pip-audit dependencies
- Semgrep security
- npm audit Worker

Install the audit commands in the app virtual environment:

```bash
cd basel-spatial-graph-main/basel-spatial-graph-v0
pip install ruff bandit pip-audit semgrep
```

## Senior-developer sparring

The repository-level `AGENTS.md` asks coding agents to act as a skeptical reviewer rather than a code-production machine:

- avoid code that does not need to exist;
- reuse before inventing;
- prefer stdlib/platform capability before adding dependencies;
- preserve validation, security and provenance even when they cost lines;
- classify review findings before changing code;
- do not perform broad “cleanup” without a concrete benefit.

This is influenced by projects such as **Ponytail**, which deliberately pushes coding agents toward a YAGNI/senior-developer mindset. Ponytail is useful as a sparring partner, not as a safety authority: independent benchmarking has also found that aggressive code reduction can lose robustness on unstated edge cases.

Reference: https://github.com/DietrichGebert/ponytail

## runO2-specific safety invariants

Generic code scanners do not understand the most important failure modes in this project. These remain explicit architectural rules:

1. **Unknown is not clean.**
2. **Measured, modelled, forecast, dynamic and unmeasured evidence remain distinguishable.**
3. **A weaker source may not silently replace a source that was validated for the claim.**
4. **The app must fail closed on the air-ranking decision if its defensible spatial baseline is unavailable.**
5. **Temporal and spatial validity scopes must remain visible.**
6. **No personal-exposure or medical claim is inferred from route comparison.**
7. **Synthetic/fixture data must never appear as real observations.**

These are defended primarily by tests and review, not by generic security tools.

## What this process does not claim

Passing all checks does **not** mean:

- the software is secure;
- the architecture is optimal;
- every dependency is trustworthy;
- the scientific inference is valid;
- the code is production-ready;
- AI-generated code is equivalent to experienced human engineering review.

It means the project has made the quality question inspectable and has introduced several independent ways to falsify its own assumptions.

That is the goal of this experiment.
