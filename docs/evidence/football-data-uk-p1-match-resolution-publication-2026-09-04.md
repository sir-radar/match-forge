# Football-Data.co.uk Phase 1B P1 match-resolution publication

Status: local acceptance-database evidence

This record appends the ten bounded P1 Football-Data.co.uk match decisions. Each
uses only the approved canonical competition and season, ordered persisted team
decisions, and provider match date. Scores, results, and aggregate statistics
were neither queried nor passed to the resolution contract.

## Publication context

- Provider ID: `01a06d67-d46d-756f-80c9-2207d0586d23`
- Competition ID: `01a051db-5565-70d1-85d4-ab6342d86baf`
- Season ID: `01a051db-5566-7286-8ad7-40d945ab8253`
- Source resource:
  `football_data_uk/mmz4281/1516/E0.csv/sha256/bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085`
- Rule version: `FootballDataUkPhase1BMatchResolutionV1`
- Decision status: `AUTO_ACCEPTED`
- Decision creation time: `2026-09-04T17:27:00+00:00`

For every row, the context-qualified StatsBomb candidate query produced exactly
one candidate with the same provider date. Each immediate identical retry
returned `verified_existing`.

| P1 row | Home label | Away label | Provider date | Canonical match ID | PostgreSQL decision ID | Decision SHA-256 |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | Bournemouth | Aston Villa | 2015-08-08 | `01a051db-5e39-7994-9706-8452d7ebc0fc` | `01a06d75-eb8a-7932-b617-16354a71d73e` | `e4fde37e3306f3fa4d92669659fd28265333e454bd89b036495309111b9b80a6` |
| 2 | Chelsea | Swansea | 2015-08-08 | `01a051db-5ccd-7471-9e9e-7c7fb91e6b0e` | `01a06d75-eb92-7f18-9eab-53f64847210b` | `22545b05f3b8cc7109030b5f299ce1f1129d6a01000be4912008d7171d43d09e` |
| 3 | Everton | Watford | 2015-08-08 | `01a051db-67fb-775b-b4c7-bd8592992f98` | `01a06d75-eb96-7b99-9caa-6ec6c893d624` | `b2d8a48c7d6d3d96d14abb88b041de9c8713fa25e7d80650cb880d249825e90b` |
| 4 | Leicester | Sunderland | 2015-08-08 | `01a051db-637c-703c-accf-e6063aaceb7b` | `01a06d75-eb9a-7342-9e5d-9b7009f1b9d4` | `c49532fe7b339d19d12d7730813e3130c6271c51d877ad4ebe8de3cac9f4ef75` |
| 5 | Man United | Tottenham | 2015-08-08 | `01a051db-5d4b-7572-bfdc-a5d3312188ce` | `01a06d75-eb9c-7510-b11d-4eb04cc912a1` | `aa2f858f1533ebb0121a7e9055b71101b9002d9fae2a404d930b362203c09e1b` |
| 6 | Norwich | Crystal Palace | 2015-08-08 | `01a051db-5e8e-70d4-acf9-d9329b005f4e` | `01a06d75-eb9e-7e12-a581-816d6a2be2cc` | `3f6fbd67f5c022b0672e17a4239caa953c05809f2ebce35fc4859535137099e0` |
| 7 | Arsenal | West Ham | 2015-08-09 | `01a051db-5eb2-734c-ae69-4ad61c2c2779` | `01a06d75-eba1-7eba-8f6d-dbebb99cd2c8` | `c2b4f9cd7f59dca9dc6183e35dfa0e0afd63dafb5eb6424e4bfd3a5db2f914b5` |
| 8 | Newcastle | Southampton | 2015-08-09 | `01a051db-5db9-7ad5-9c05-308ddfead520` | `01a06d75-eba3-7af6-9d6d-b007a9c17fcb` | `c7537baa45c8c50f0d92b2df7ec039174ed4616364edc6cb85caca503787b998` |
| 9 | Stoke | Liverpool | 2015-08-09 | `01a051db-5ad6-7962-a66d-64a8a4b1b1a4` | `01a06d75-eba5-7831-9593-320647c459e6` | `7acdbbb4dfb563356dc89c863dd990bcd9996d0a35052dc757e5baf6a58aff60` |
| 10 | West Brom | Man City | 2015-08-10 | `01a051db-5f08-7058-b134-a7c00fde5498` | `01a06d75-eba6-7f45-9514-a68d38fa88fe` | `5c00f9fc413d0cbe28ba996791a08ba2e120f962d689ac3768bc67fb914e9fec` |

This establishes bounded identity evidence only. The next work must preserve
field-level conflicts and quarantine semantics before trusted canonical
publication. Sprint 2 remains `FAIL`; Phase 3 remains blocked.
