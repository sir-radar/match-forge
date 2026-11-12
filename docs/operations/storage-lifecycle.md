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
previous measurements and provide retry. Resource actions are described in
[Resource management](#resource-management) below.

An owner receipt binds an exact immutable manifest, resource IDs and expiration.
`REVIEWED` and `REJECTED` are audit dispositions, not deletion permissions.
SQL rejects `QUARANTINED` and `DELETED` transitions on review records. Dry-run
plans include blockers, recovery coverage, a minimum grace deadline and rollback
requirements. Unknown physical savings remain null. A review receipt never turns
into deletion permission; resource actions use their own approval below.

## Resource management

Migration `202611120100_storage_resource_management` adds append-only
`storage_protections`, `storage_database_evidence` and `storage_dispositions`,
and the durable `storage_operations` history. Storage Management lists every
database in the API's cluster, every Git worktree and, when the policy declares
`managed_roots`, the direct children of those roots. Each resource has a
server-computed class:

| Class | Meaning | Actions |
| --- | --- | --- |
| Protected | Authoritative or required database, active consumers, managed rehearsal lease, primary or locked worktree, protected path, owner protection, or an unverifiable authoritative identity | None. Not selectable. No override exists. |
| Review required | Not yet compared, stale evidence, unique rows, uncommitted or unpushed work, unknown ignored files, incomplete measurement, symlink | None until remediated or resolved by an owner disposition |
| Eligible | Database with current evidence of no unique canonical identities; worktree that is clean, pushed and holds only regenerable ignored output; child of an owner-declared disposable root | Delete; Quarantine (databases and files) |

Identity is immutable: databases by cluster system identifier and OID (renaming
keeps protection), files by device and inode, worktrees by their Git directory.
The API registers the database it is connected to as the authoritative
operating database on first use. If the connected database later differs, all
database actions are disabled until the identity is verified again. Changing
the authoritative database needs a separately governed forward migration.

Workflow for an existing resource:

1. **Compare** a database with the operating database. The read-only comparison
   records which canonical identities exist only in the candidate.
2. **Resolve review.** Reconcile valid unique data through the normal admission
   controls, or record an owner disposition (`UNIQUE_DATA_NOT_REQUIRED` or
   `PRESERVE`) bound to that exact evidence digest. New evidence voids it.
3. **Preview** the action. The plan lists exact resources, blocked resources
   with reasons, unique expected savings and consequences. Blocked resources do
   not stop independent eligible ones.
4. **Approve and execute** with the owner credential (the `MATCHFORGE_ADMIN_CLI_TOKEN`
   Bearer value) and, for Delete and Permanently delete, the typed phrase
   `DELETE <n>`. The server recomputes the plan and rejects any change.
5. **Execution** runs one resource at a time. Each operation is re-assessed just
   before it runs; a database trigger rejects any protected identity. Databases
   are fenced with `ALLOW_CONNECTIONS false` and dropped without `FORCE`; files
   are removed through an `os.Root` handle bound to the managed root; worktrees
   are removed with `git worktree remove` without `--force`, keeping the branch.
6. **Measurement.** A deletion is recorded as succeeded only after the resource
   is verified absent, with its measured size and the host free space before
   and after. Database bytes are released inside the PostgreSQL volume; the
   host gains space only when the Docker VM returns freed blocks.

Quarantine renames a database to `matchforge_quarantine_<oid>` with connections
disabled, or moves a file tree into the root's `.matchforge-quarantine`
directory on the same device. Restore reverses it when the original name or
path is free. Quarantine frees no space; Permanently delete does. A restart
cancels pending operations and marks interrupted ones failed unless the exact
resource is verifiably absent.

### Policy-managed automation

Scheduled work stays read-only unless the policy file declares an
`automatic_cleanup` rule. Two rule kinds exist, and both apply only to direct
children of a `managed_roots` entry with class `disposable`:

```json
"managed_roots": [{ "path": "/abs/cache-root", "class": "disposable", "description": "regenerable build cache" }],
"protected_paths": ["/abs/cache-root/keep"],
"automatic_cleanup": [{ "action": "DELETE_DISPOSABLE", "root": "/abs/cache-root",
  "min_age_seconds": 604800, "max_per_run": 20,
  "approved_by": "owner", "approval_record": "docs/governance/decision-events/<file>" }]
```

`PURGE_EXPIRED_QUARANTINE` permanently deletes quarantined items from that root
after the quarantine retention. Validation refuses rules without an approval
record, with more than 100 items per run, with less than one day of age, or on a
root that is not disposable. Databases, worktrees, review roots and protected
paths are never selected. Each run is limited to the policy's
`interval_seconds`, goes through the same preview, revalidation, database
protection trigger and measurement as a manual action, and is recorded with the
actor `policy:<approval_record>:<approved_by>`.

Deploying these controls authorizes nothing. Each existing-resource deletion
still needs the owner's resource-specific approval through this workflow.

## Recovery and approval

For each existing resource, record its exact identity, dependencies, active use,
verified independent recovery, expected unique physical savings, retention and
rollback. Obtain resource-specific approval before a destructive action. A review
receipt records an audit disposition only. Backups are not pruned and no
physical database maintenance runs.

Recover archived evidence into a new directory and verify the manifest and all
original hashes before changing readers. Preserve original registrations for
unavailable dependencies and use the existing governed correction process.

Verification covers repository checks, disposable PostgreSQL migrations,
archive integrity, shared-work ownership, and dashboard browser behavior.
