# runO2 agent review rules

This repository is intentionally built with heavy AI assistance. Treat every generated change as a proposal, not as evidence that the code is correct.

## Before adding code

Prefer, in order:

1. deleting or avoiding the requirement if it is not needed;
2. reusing an existing path in the repository;
3. Python/browser/platform standard functionality;
4. an already-installed dependency;
5. the smallest explicit implementation that preserves the trust boundaries below.

Do not trade away validation, provenance, error handling, accessibility, security or reproducibility merely to reduce line count.

This is inspired by the senior/YAGNI review style popularised by the Ponytail project, but these repository rules are deliberately independent and are not a substitute for tests or security tools.

## Review every AI-written change against these questions

### Correctness
- What claim does this code make?
- Is that claim covered by a deterministic test or source evidence?
- What happens for missing, malformed and stale inputs?
- Is fixture/synthetic data visibly distinguishable from real data?

### Architecture
- Is this the smallest layer that can own the behavior?
- Does it duplicate an existing abstraction?
- Does it introduce a dependency for something the platform or stdlib already does?
- Does a failure degrade honestly, or silently switch to weaker evidence?

### Evidence boundary
- Never blend measured, modelled, forecast, dynamic and unmeasured values into one unexplained score.
- Unknown is not clean.
- A weaker dataset may not silently replace a stronger one when the stronger source is unavailable.
- Preserve temporal scope, spatial scope and provenance to the output.

### Security
- Treat network responses, query parameters, uploaded/downloaded data and environment variables as untrusted inputs.
- Avoid shell construction from user-controlled input.
- Do not log secrets or credentials.
- Prefer deny/fail-closed behavior at trust boundaries.
- New dependencies require a reason and should be checked for known vulnerabilities and maintenance risk.

### Review output
When asked for a review, return findings before fixes and classify them as:
- **must fix** — correctness/security/data-integrity issue;
- **should fix** — maintainability/robustness issue with plausible impact;
- **consider** — simplification or design improvement;
- **not an issue** — tempting cleanup that does not justify churn.

Do not rewrite large areas merely to make them stylistically uniform.
