# Source notes — milestone 2

## Pinned calendar

- Official entry point: https://www.uvic.ca/calendar/undergrad/index.php
- Verified heading: Undergraduate calendar - September 2026.
- Catalog ID published by that page: `69bd9d92e76504efd3e57c74`.
- The catalog's own metadata confirms its title and September 1–December 31, 2026 date range.
- Course API used by the calendar application: `https://uvic.kuali.co/api/v1/catalog/course/{catalog_id}/{pid}`.
- Course schema provides the actual field labels, including “Prerequisites” and “Pre- or corequisites”.

The importer pins the catalog ID rather than following whichever edition becomes current. Raw API responses, schema, listing, catalog metadata, and per-response provenance are stored locally. Retrieval timestamps come from the fetch, not the calendar edition. Original HTML remains available alongside extracted text so nested requirement structure can be checked.

## Access and reuse review

Reviewed UVic's public robots.txt, terms of use, and copyright information. The calendar route is not disallowed in UVic's robots.txt. The source data is available through the public calendar without credentials. Requests are sequential with a short delay and a descriptive user agent; the offline option avoids repeated downloads.

- https://www.uvic.ca/robots.txt
- https://www.uvic.ca/info/terms-of-use/index.php
- https://www.uvic.ca/info/copyright-information/index.php

UVic's copyright notice does not provide a blanket open-content license. Keep downloaded data local and excluded from Git. Revisit the intended use of excerpts and source material before public deployment; public availability does not establish a redistribution license.

## Manual extraction review

Checked all six saved records against extracted sections:

| Course | Checked behavior |
| --- | --- |
| CSC110 | Alternative prerequisite branches and credit exclusion retained |
| CSC115 | Alternative programming prerequisites and exclusion retained |
| CSC225 | Both prerequisite groups, each containing alternatives, retained |
| CSC226 | Prerequisites and concurrent-enrollment alternatives remain separate; former course and exclusion retained |
| CSC320 | Required course plus an alternative prerequisite group retained |
| CSC360 | Required courses plus two separate alternative groups retained |

CSC115 contains apparent editorial wording in its official description. The importer flags this and preserves the original; it does not silently rewrite it. The project has not yet implemented answers or measured their accuracy.

Ten development questions cover descriptions, nested alternatives, concurrency, credit exclusions, an unanswerable question, and an ambiguous question. These are development examples, separate from the future held-out test set.
