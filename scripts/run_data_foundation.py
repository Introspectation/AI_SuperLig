#!/usr/bin/env python3
"""Reproduce the complete audited data foundation with one offline command."""

from __future__ import annotations

import build_canonical_data
import run_data_audit


def main() -> int:
    audit_status = run_data_audit.main(["--offline"])
    if audit_status != 0:
        return audit_status
    return build_canonical_data.main()


if __name__ == "__main__":
    raise SystemExit(main())
