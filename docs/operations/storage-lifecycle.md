# Storage lifecycle management

Storage reviews collect managed resource usage, budget alerts and proposed
retention actions. The Admin view uses the existing Work Orchestrator and backup
workflow. Operating activation requires the matching release and an explicit policy.

## Registry and ownership

SQL migrations own `storage_resources`, immutable `storage_reviews` and
`storage_approvals`, and job-owned `storage_reservations`. These describe storage
and reference the existing `work_items`; they do not replace provider, source,
forecast or model registrations. Discovery never removes protection or infers
reconstructability from a filename or age. Managed rehearsal ownership matches
the PostgreSQL system identifier, database OID and parent work record, not its
name alone.

Daily reviews use `STORAGE_LIFECYCLE` in the existing `CommandSyncRunner`, BULK
exclusion and Work Orchestrator. Publication checks the current shared lease
before and after its transaction. A work ID cannot bind a different review on
retry. Reviews retain the actual policy, its hash, resource observations,
capacity, alerts and proposed actions. Bounded scans report incomplete measurements
as lower bounds; missing paths, symlinks and unreadable resources block eligibility.
Worktree discovery retains dirty, unmerged, unpushed or otherwise unverified work.
Caches outside explicitly managed project roots are not touched.

Capacity admission serializes reservations by backing device, rereads free capacity
while holding that lock, and preserves recovery headroom. Release uses the same
lock. Expired reservations remain charged until their exact owner releases them;
an expired lease never proves that files or databases disappeared. PostgreSQL
admission checks both the host and the verified Docker/PostgreSQL volume, including
the cluster budget and other unreleased reservations.

The fixture launcher creates only a fresh random database, sets the existing
persistent experimental marker, records ownership before starting its child and
pins both database environment variables. It checks the original OID before
teardown and releases only that new fixture target, including after child failure.
It never adopts an old database. A crash leaves a charged resource for review.
Use this launcher only for disposable fixtures or reconstructable test replays;
unique acquisitions, authoritative evaluation results and durable evidence must
not be placed in a disposable target. The launcher grants no scientific or provider
authorization. Children must consume the supplied URLs and must not reload `.env`.

## Capacity policy and activation

Copy the [policy template](../../infrastructure/storage-policy.example.json) to
a durable location and replace the placeholder paths and zero capacities. Set
disjoint canonical roots, measured subsystem warning and critical limits, and
headroom for verified recovery. Derive the PostgreSQL budget from measured
cluster usage and the peak size of one expected rehearsal. The template cannot
be activated until all required capacities are set.

After the matching release and migrations are deployed, set
`MATCHFORGE_STORAGE_POLICY` to the reviewed file and restart the existing API.
An empty setting disables scheduled submission. Verify a completed dry-run
review and the existing backup preflight. Scheduled backup attempts use the
same preview, encrypted capture, readback and isolated restore as manual backups.
The configured interval and existing shared work exclusion control dispatch.

## Archive and fixture commands

`make build` produces `.local/bin/matchforge-storage`. Allocation commands require
the producing job's active common work ID, owner, original claim token, generation
and explicit capacity policy. The worker must keep its normal heartbeats. Use the
original lease from the job that is allocating storage.

```sh
.local/bin/matchforge-storage -action pack \
  -policy "$MATCHFORGE_STORAGE_POLICY" -work-id "$WORK_ID" -owner "$WORK_OWNER" \
  -lease-token "$LEASE_TOKEN" -generation "$WORK_GENERATION" \
  -source "$EVIDENCE_ROOT" -destination "$NEW_ARCHIVE" \
  -retain-until "$MINIMUM_HOLD_UNTIL" -file-list "$MEMBERS_JSON"

.local/bin/matchforge-storage -action verify -source "$NEW_ARCHIVE"
.local/bin/matchforge-storage -action read -source "$NEW_ARCHIVE" original/path.json

.local/bin/matchforge-storage -action restore \
  -policy "$MATCHFORGE_STORAGE_POLICY" -work-id "$WORK_ID" -owner "$WORK_OWNER" \
  -lease-token "$LEASE_TOKEN" -generation "$WORK_GENERATION" \
  -source "$NEW_ARCHIVE" -destination "$NEW_EMPTY_DESTINATION"

.local/bin/matchforge-storage -action rehearse-fixtures \
  -policy "$MATCHFORGE_STORAGE_POLICY" -work-id "$WORK_ID" -owner "$WORK_OWNER" \
  -lease-token "$LEASE_TOKEN" -generation "$WORK_GENERATION" \
  -estimated-bytes "$PEAK_ADDITIONAL_BYTES" -- command-with-explicit-fixture-inputs
```

Member lists are bounded JSON arrays of original relative paths. For large trees,
use bounded batches rather than one unbounded manifest. The container stores each
SHA-256 blob once in a streaming gzip/tar payload and preserves every original
pathname, size, hash, modification time and mode in its versioned manifest. The
reader verifies payload, member lengths/hashes, gzip checksum and complete member
coverage. Unsupported metadata, traversal, symlinks and ownership failures are
rejected. Publication commits when the verified manifest is linked into an
exclusive new destination after syncing its payload. Retries verify the exact
published bytes. The registry records the producing work, retention deadline,
manifest hash and verified logical, unique and packed sizes. Compression that
does not reduce representation size is rejected.

Restore always creates a new directory, writes owner-only files and retains the
original modes as metadata. A minimum hold deadline does not remove the independent
protected flag. Expiration is not deletion permission. Failed or interrupted staging
is protected until ownership and dependencies are verified; there is no blanket TTL.

## Database hygiene and Admin

A new trigger skips `product_competitions` updates when every field except
`updated_at` is unchanged. Observation/source timestamps remain in their own
registrations. Real read-model changes still write, and invalid values still face
their normal constraints. No existing row is rewritten and no vacuum, repack,
table rewrite or bloat maintenance runs.

`/admin/storage` follows the existing Backup Admin layout and Tailwind tokens.
It shows capacity, accounting by subsystem, protected resources, blockers, alerts,
history, archive savings, manifest identity and review receipts. Archive receipts
show the verified representation sizes and observation time. Backup storage and
recovery are an independent server resource,
so a disconnected drive does not hide storage observations. Existing Data Sync
and shared-work views show lifecycle attempts and cancellation. Read failures retain
previous measurements and provide retry. Destructive controls are absent.

An owner receipt binds an exact immutable manifest, resource IDs and expiration.
`REVIEWED` and `REJECTED` are audit dispositions, not deletion permissions.
SQL rejects `QUARANTINED` and `DELETED` transitions. Dry-run plans include blockers,
recovery coverage, a minimum grace deadline and rollback requirements. Unknown
physical savings remain null. There is no environment switch or API that turns a
review receipt into arbitrary filesystem or database deletion.

## Recovery and approval

For each existing resource, record its exact identity, dependencies, active use,
verified independent recovery, expected unique physical savings, retention and
rollback. Obtain resource-specific approval before considering a destructive
action. A review receipt records an audit disposition. This release does not
execute quarantine, remove existing resources, prune backups or perform physical
database maintenance.

Recover archived evidence into a new directory and verify the manifest and all
original hashes before changing readers. Preserve original registrations for
unavailable dependencies and use the existing governed correction process.

Verification covers repository checks, disposable PostgreSQL migrations,
archive integrity, shared-work ownership, and dashboard browser behavior.
