# Contributing

## Branch model

`main` is the stable branch. New work starts from an up-to-date `main` on a
short-lived branch such as:

```text
agent/phase0-data-audit
```

The normal flow is:

```text
main -> working branch -> commits -> push -> draft PR -> CI -> review -> merge
```

A branch is a movable pointer to a commit history, not a second physical copy
of the project. A pull request shows the difference between the working branch
and `main`. CI checks the proposed history before it is merged.

## Commit format

Use an answer-first date and summary, followed by concrete bullets:

```text
08.08.2026 -> genel yapilan is

- Birinci somut degisiklik.
- Ikinci somut degisiklik.
- Onemli sinir veya karar.
```

Keep unrelated work in separate commits. Never commit `.env` files, access
tokens, private datasets, or credentials to this public repository.

## Raw-data rule

Files under `data/raw/football_data/` are immutable snapshots. Do not edit,
normalize, re-save, or overwrite them. A source refresh requires explicit
review, updated checksums, a regenerated audit, and an explanation in the
commit body.
