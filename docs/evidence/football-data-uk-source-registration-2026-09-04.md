# Football-Data.co.uk Phase 1B source registration

Status: local acceptance-database evidence

This record appends PostgreSQL source-lineage evidence for the frozen
Football-Data.co.uk Phase 1B receipt bundle. It does not publish canonical
facts, resolve entities, reconcile conflicts, or decide the Phase 1B/2B gate.

## Registered identity

- Provider code: `football_data_uk`
- Provider name: `Football-Data.co.uk`
- Provider source type: `file_download`
- Provider ID: `01a06d67-d46d-756f-80c9-2207d0586d23`
- Source identity: `football_data_uk/phase1b/frozen-resource-bundle`
- Source snapshot ID: `01a06d67-d471-7cf8-867c-accb9f73dcde`
- Source revision and receipt-bundle SHA-256:
  `507d51f57ebcda6565d5877823cd57f12720fe7f26c02a2e279f26691843f955`

The source snapshot references the already immutable receipt bundle at:

```text
manifests/provider=football_data_uk/
acquisition_sha256=507d51f57ebcda6565d5877823cd57f12720fe7f26c02a2e279f26691843f955/
acquisition-evidence-v1.json
```

## Registered resources

| Provider path | Raw SHA-256 | Bytes | Parse status | Validation status |
| --- | --- | ---: | --- | --- |
| `notes.txt` | `6ecd41a98ad2751372817e7e6f1709bfeb433c53dd9aeda330fd926a5471452d` | 7,686 | `not_applicable` | `valid` |
| `mmz4281/2526/E0.csv` | `3e3a8352f9ada6789c508d6ca184424421fed56a30400904a4a327c583407e62` | 203,438 | `pending` | `pending` |
| `mmz4281/1516/E0.csv` | `bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085` | 100,656 | `pending` | `pending` |

Registering the identical bundle again returned the same provider, snapshot,
and resource identities. No raw provider byte was copied, changed, or made
canonical.

The next bounded proof step is append-only persistence of the approved team and
context-only match `ResolutionDecisionV1` records. Sprint 2 remains `FAIL` and
Phase 3 remains blocked.
