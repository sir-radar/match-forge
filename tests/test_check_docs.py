from scripts import check_docs


def test_placement_rejects_root_scratch_report_and_stray_json() -> None:
    findings = check_docs.placement_findings(
        [
            "README.md",
            "NOTES.md",
            "docs/feature-progress.md",
            "docs/NEW_FEATURE_REPORT.md",
            "docs/V4_IMPLEMENTATION_REPORT.md",
            "docs/operations/result.json",
            "docs/evaluation/inputs.json",
            "docs/evidence/anything-draft.json",
            "docs/temporal-model.md",
            "web/test-fixtures/backup-status.json",
        ]
    )
    flagged = sorted({finding.split(":")[0] for finding in findings})
    assert flagged == [
        "NOTES.md",
        "docs/NEW_FEATURE_REPORT.md",
        "docs/feature-progress.md",
        "docs/operations/result.json",
    ]


def test_links_and_anchors_resolve_outside_code() -> None:
    read = {
        "docs/README.md": "# Index\n[a](guide.md#set-up-make-dev) [b](missing.md) [c](guide.md#nope)\n`[d](gone.md)`\n```\n[e](gone.md)\n```\n[web](https://example.com)\n",
        "docs/guide.md": "# Guide\n## Set up `make dev`\n",
    }
    findings = check_docs.link_findings(sorted(read), read)
    assert findings == [
        "docs/README.md:2: broken link to docs/missing.md",
        "docs/README.md:2: missing anchor #nope in docs/guide.md",
    ]


def test_historical_records_are_not_link_checked() -> None:
    read = {"docs/evidence/old.md": "[x](removed.md)\n", "docs/README.md": "# Index\n"}
    assert check_docs.link_findings(sorted(read), read) == []


def test_every_maintained_document_is_reachable_from_the_index() -> None:
    read = {
        "docs/README.md": "[contracts](contracts/)\n[guide](guide.md)\n",
        "docs/guide.md": "[deep](deep/topic.md)\n",
        "docs/deep/topic.md": "",
        "docs/contracts/a-v1.md": "",
        "docs/orphan.md": "",
        "docs/evidence/record.md": "",
    }
    findings = check_docs.index_findings(sorted(read), read)
    assert [finding.split(":")[0] for finding in findings] == ["docs/orphan.md"]


def test_duplicate_headings_get_numbered_anchors() -> None:
    assert check_docs.anchors("# A\n## Notes\n## Notes\n") == {"a", "notes", "notes-1"}
