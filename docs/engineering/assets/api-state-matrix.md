# Admin data-sync API state matrix

| Resource | State | UI treatment | Test |
|---|---|---|---|
| Run list and coverage | loading | Loading labels; actions remain visible | component test |
| Run list and coverage | success | Coverage metrics and recent runs | component and browser tests |
| Run list | empty | “No manual sync runs yet.” | component contract |
| Run list | malformed | Boundary parser rejects payload; actionable response error | contract parser and component error path |
| Run list | network/API failure | Alert with status detail and retry | component test |
| Start mutation | submitting | Selected button says “Starting…”; all actions disabled | component test |
| Start mutation | accepted | Queued/running live region and polling | component and browser tests |
| Start mutation | 409 | Active-run explanation, then list refresh | Go and component behavior |
| Start mutation | provider/parser/database failure | Persisted FAILED run and exact failure reason in history | Go runner and UI history |
| Poll | queued/running | Retained list, elapsed time, current phase when supplied | component behavior |
| Poll | succeeded | Reload authoritative list and coverage | component behavior |
| Poll | failed | Reload authoritative failure and summary | component behavior |
| Navigation/unmount | any request | Abort initial request; clear poll and clock timers | component implementation |

No optimistic success state is used. Server state remains authoritative.
