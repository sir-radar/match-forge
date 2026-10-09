# Governed commit invariants

A committed artifact must never be required to contain the SHA of the commit
that contains that artifact. Git commit identity depends on committed content,
so that requirement is circular.

For governed executions that require committed preregistration, use two roles:

```text
SOURCE_COMMIT
    complete executable scientific implementation

EXECUTION_COMMIT
    direct child containing only frozen experiment-control files
```

Before outcome access, require a clean worktree, verify that the execution
commit's parent equals the preregistered source commit, reject executable source
changes in the execution commit, and verify a deterministic scientific-source
tree hash plus all frozen file and artifact hashes.
