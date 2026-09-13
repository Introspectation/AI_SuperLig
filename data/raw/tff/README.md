# TFF kickoff snapshot

`kickoff_times_2017-19.csv` is an immutable, source-derived snapshot of the
selected-week fixture rows published in the official TFF league archive. TFF
does not provide these rows as a downloadable CSV, so the acquisition script
extracts only the match identity, result, date, and kickoff time required for
the missing-time backfill.

The snapshot is not a byte-for-byte copy of the HTML pages. Its adjacent
manifest records every source URL plus the SHA-256 and byte size of each HTML
response used to produce it. The acquisition command refuses to overwrite an
existing snapshot or manifest.

Acquisition command:

```powershell
python scripts/bootstrap_tff_kickoffs.py
```

Normal audits and canonical builds are offline and do not call TFF.
