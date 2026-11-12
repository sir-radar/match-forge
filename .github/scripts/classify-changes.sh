#!/usr/bin/env bash
set -euo pipefail

base=${1:-}
zero_sha=0000000000000000000000000000000000000000

requires_full_ci() {
  local path=$1 grep_status

  case "$path" in
    *.md|*.mdx|*.rst)
      return 1
      ;;
    # Project status discovers owner decisions by glob. V4 qualification
    # constructs report names, and evaluation tools select inputs by path.
    docs/project-status.json|docs/evidence/owner-decision-*.json|docs/evidence/v4-issue-02-*.json|docs/evaluation/*.json|docs/contracts/*.json|*.schema.json)
      return 0
      ;;
    docs/*.json)
      # Search both trees so a deleted or renamed input still counts.
      # Include non-prose configuration and manifests as possible consumers.
      if git grep -IFq -e "${path##*/}" "$base" HEAD -- \
        ':(exclude,glob)**/*.md' ':(exclude,glob)**/*.mdx' ':(exclude,glob)**/*.rst' \
        ":(exclude,top,literal)$path"; then
        return 0
      else
        grep_status=$?
      fi
      if [[ "$grep_status" != 1 ]]; then
        printf '::warning::Could not check JSON references; running full CI.\n' >&2
        return 0
      fi
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

if [[ -z "$base" || "$base" == "$zero_sha" ]] ||
  ! git cat-file -e "$base^{commit}" 2>/dev/null; then
  printf 'code_changed=true\n'
  exit 0
fi

git diff --check "$base" HEAD >&2
changed_paths=$(mktemp)
trap 'rm -f "$changed_paths"' EXIT
git diff --name-only --no-renames -z "$base" HEAD > "$changed_paths"

while IFS= read -r -d '' path; do
  if requires_full_ci "$path"; then
    printf 'code_changed=true\n'
    exit 0
  fi
done < "$changed_paths"

printf 'code_changed=false\n'
