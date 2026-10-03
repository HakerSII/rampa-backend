# F29 — Multi-worker consistency (several uvicorn workers / instances on one database)

Overview: [../../README.md](../../README.md) · extends F9 (SQL write-behind cache)

- Table `meta(key, value)` holds `data_version`. Every request starts with `UseCases.sync()`: one `SELECT`; if the version moved (another worker committed) → reload the cache and continue id sequences.
- Commit = optimistic lock: `UPDATE meta SET value = value + 1 WHERE value = <loaded>` in the same transaction as the writes. 0 rows → rollback, reload, HTTP **409 CONFLICT** "concurrent update — retry". Commits without changes skip the check.
- Memory mode: `sync()` is a no-op. Cost: one indexed single-row read per request.
- Limits: last-writer-loses on a race (client retries); not for high write throughput.
