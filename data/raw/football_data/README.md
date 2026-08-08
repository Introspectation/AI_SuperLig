# Football-Data raw snapshots

This directory contains byte-for-byte CSV snapshots downloaded from the
Football-Data Turkish league page:

https://www.football-data.co.uk/turkeym.php

Files in this directory are immutable inputs. The audit tooling must never
repair, normalize, or overwrite them. Any future source refresh must be an
explicitly reviewed replacement with new checksums and regenerated reports.

Git line-ending conversion is disabled for these CSVs in `.gitattributes` so
that a Windows checkout does not mutate the downloaded bytes.

