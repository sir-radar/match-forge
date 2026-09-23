# Provider clarification inquiry drafts — 2026-09-23

Status: `READY_TO_SEND — ACTION-TIME CONFIRMATION REQUIRED`.

Authorized by
[the owner decision](owner-decision-authorize-provider-clarification-inquiries-2026-09-23.md).
No message has been sent. These drafts request written clarification only; they
do not request data delivery, purchase, trial, marketing contact, another API
audit, ingestion, or provider activation.

## PitchAPI

No official email, contact form, legal entity, Terms URL, or Privacy URL could
be verified on [PitchAPI](https://pitchapi.dev/) or its
[PyPI package](https://pypi.org/project/pitchapi/). Do not invent an address such
as `support@pitchapi.dev`.

The only provider-attributed inbound route found is the developer's
[public Reddit feedback thread](https://www.reddit.com/r/sportsanalytics/comments/1w2n53i/update_pitchapi_2_weeks_live_15m_requests_served/).
It is not a verified legal/support channel. The first contact should therefore
request a formal private channel without publishing the owner's email address:

```text
Hi — I am evaluating PitchAPI for a private, non-commercial reproducible
football-research project. Is there an official support or legal contact for
questions about xG source/model versions, retention, corrections, identifier
stability, numeric limits, and a metadata-only Bundesliga 2023/24 and Ligue 1
2022/23 shot-coverage manifest? I am not requesting data delivery, a trial,
purchase, or marketing contact. Thank you.
```

After PitchAPI supplies a verified private channel, send:

```text
Subject: Non-binding data-governance questions — Bundesliga 2023/24 and Ligue 1 2022/23

Hello PitchAPI team,

I am the MatchForge repository owner. I am assessing PitchAPI for
MatchForge, a private, non-commercial football research project. This is a
non-binding information request only. I am not requesting data delivery, a
purchase, a trial, or marketing communications.

Could you confirm in writing:

1. The legal entity operating PitchAPI and the applicable terms, privacy notice,
   and data-use terms.
2. The upstream provider for shot events and shot-level xG in men's Bundesliga
   2023/24 and Ligue 1 2022/23.
3. The xG model owner, name, and version for each season; whether one unchanged
   version covers every match and both seasons; and any backfills or model
   changes.
4. Whether every played match has complete shot-level xG, penalty identification,
   and period/half identification. If available, please provide a metadata-only
   coverage manifest for all 306 Bundesliga and 380 Ligue 1 matches, listing
   match ID, endpoint availability, shot count, missing-xG count, and known
   exclusions or corrections. No shot or event payload is requested.
5. Your correction/version policy, including in-place historical changes,
   notification and timestamps, prior-version availability, ID stability, and
   mappings after ID rebuilds.
6. Permitted raw-response and immutable-snapshot retention for private research,
   required attribution, and restrictions on automated qualification, internal
   derived datasets, or aggregate publication.
7. Numeric burst, concurrency, retry, pagination, response-size, and fair-use
   limits.

A concise written response or links to authoritative documentation would be
sufficient.

Regards,
[repository owner — reply address intentionally omitted from source control]
```

## API-Football / API-Sports

Official channel: authenticated support in the
[API-Football dashboard](https://dashboard.api-football.com/). Free-account
support availability is not publicly guaranteed.

```text
Subject: Private research snapshot retention and post-access use clarification

Hello API-Sports Support,

I use API-Football for MatchForge, a private, non-commercial football-research
project. The project is not distributed and does not publish, resell or expose
API source data.

Could you confirm whether your terms permit:

1. Indefinite private, access-controlled retention of exact API JSON responses,
   request metadata and SHA-256 hashes for reproducibility and audit.
2. Continued internal use after API access, a plan or the account ends, without
   refreshing, displaying, publishing, redistributing or reselling source data.
3. Preserving earlier immutable snapshots when records are corrected, while
   appending newer snapshots.
4. Retaining internal derived aggregates and audit reports after access ends.
5. Any required attribution for private research or unpublished derived reports.
6. Any caching, deletion or maximum-retention limits.
7. Any extra restrictions for Bundesliga 2023/24 or Ligue 1 2022/23.

During a bounded test, `/status` reported usage 0 and daily limit 100. Response
headers then decreased from 100 to 91 across nine requests, while the next
request reported 99 with no reset header. Which value is authoritative, and is
that header daily, rolling or per-minute capacity?

I request only a written answer and conditions. Please do not deliver data,
activate a trial, initiate a purchase/subscription, or treat this inquiry as
marketing consent.

Regards,
[repository owner — reply address intentionally omitted from source control]
```

## football-data.org

Official destination: `info@football-data.org`.

```text
Subject: Private research snapshot retention and post-access use clarification

Hello Football-Data.org,

I am evaluating the free Football-Data.org API for MatchForge, a private,
non-commercial football-research project. The project is not distributed and
does not publish, resell or expose API source data.

Could you confirm whether your terms permit:

1. Indefinite private, access-controlled retention of exact API JSON responses,
   request metadata and SHA-256 hashes for reproducibility and audit.
2. Continued internal use after the free subscription or account ends, without
   refreshing, displaying, publishing, redistributing or reselling source data.
3. Preserving earlier immutable snapshots when records are corrected, while
   appending newer snapshots.
4. Retaining internal derived aggregates and audit reports after access ends.
5. Whether the required attribution applies to private internal documentation
   or only to public apps and websites.
6. Any caching, deletion or maximum-retention limits.
7. Whether clause 9.1's post-cancellation restriction also covers an unpublished
   internal research archive and reproducibility checks.

I request only a written answer and conditions. Please do not deliver data,
activate a trial, initiate a purchase/subscription, or treat this inquiry as
marketing consent.

Regards,
[repository owner — reply address intentionally omitted from source control]
```

## Football-Data.co.uk

Published terms support bounded manual private league-prediction research but
block automation and leave immutable retention unclear. Official destination,
rendered as an image on the [contact page](https://football-data.co.uk/contact.php):
`joseph@football-data.co.uk`.

```text
Subject: Private non-commercial research use clarification — no data request

Hello,

I maintain MatchForge as a private, non-commercial football-model research
project. It is not distributed, published, sold or used as a public data
product. I understand that automated bots/scrapers and commercial AI or
data-training products are not permitted, and I will follow those limits.

Could you confirm whether I may manually download published CSV files for
private statistical model research, retain them internally as immutable
checksum-identified snapshots, and continue using those snapshots and derived
model artifacts if the website file later changes or is removed? Please also
state any required attribution. I will not redistribute source data or automate
retrieval without separate written permission.

This is only a terms clarification. Please do not send data, create a trial,
propose a purchase, or add me to marketing communications.

Regards,
[repository owner — reply address intentionally omitted from source control]
```

## Understat

Official destination: `support@understat.com`, published on
[Understat](https://understat.com/).

```text
Subject: Private non-commercial research permission clarification — no data request

Hello Understat Support,

I maintain MatchForge as a private, non-commercial football-model research
project. It is not distributed, published, sold or used as a public data
product.

Before accessing data beyond ordinary page viewing, could you confirm:

1. Whether complete match and shot records for Bundesliga 2023/24 and Ligue 1
   2022/23 may be acquired for private research.
2. Whether automated or bulk access is permitted and the approved endpoint,
   export, credentials, cadence and limits.
3. Whether records may be retained internally as immutable checksum-identified
   snapshots for reproducibility.
4. Whether snapshots and derived model artifacts may remain in use after access
   ends or public data changes.
5. Required attribution.
6. Whether private statistical-model research is permitted when source data are
   never redistributed.

I will use only a method you explicitly permit. I am not requesting data
delivery, an account, trial, purchase, or marketing contact.

Regards,
[repository owner — reply address intentionally omitted from source control]
```

## Action-time confirmation

Sending these emails, dashboard messages, or public comments is external
communication performed as the owner. Browser policy requires confirmation
immediately before send/post actions even though the research scope is already
approved.
