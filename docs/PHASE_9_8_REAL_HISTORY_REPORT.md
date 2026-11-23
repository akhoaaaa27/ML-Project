# Phase 9.8 — Real forecast publication and Prediction History

The Windows real service ran with publication disabled. Its real ledger reader returned zero records before and after verification, and no real ledger directory was created. The preview path resolved an upcoming eligible match with the frozen model. The authorized write path was exercised in isolated test storage.

## Authorized local publication

1. Run the real-data preflight and select an actual `READY` or `EARLY_READY` fixture. Confirm the runtime snapshot and compare the evidence expiry and kickoff with UTC now.
2. Preview read-only and inspect model identity, frozen inputs and provenance. The CLI probe with `--fixture` shows the ordered features, historical windows, provider evidence, cutoff and both hashes. The HTTP preview exposes the selected history SHA-256 and feature SHA-256 without exposing all raw inputs.
3. Obtain an explicit operator decision for this particular forecast. The operator starts a fresh same-machine server with a strong temporary operator token in its process environment. Use a prompt that does not echo the token and keep it out of command arguments, repository files, browser scripts, URLs and screenshots. The API also enforces its localhost host and origin checks.
4. Recheck preview against the running server. After explicit authorization, submit its two hashes with the fixture key as an expected input binding. The server recomputes eligibility and inference, compares the hashes before append, and returns 409 if inputs changed. A first successful write returns `PUBLISHED`, `INITIAL`, revision 1. A retry on the same inputs returns the existing record as `NO_CHANGE`.

```powershell
$api = 'http://127.0.0.1:8765/api/v1'
$body = @{ fixture_key = $selectedFixtureKey }
$probe = Invoke-RestMethod "$api/forecasts/preview" -Method Post -ContentType 'application/json' -Body ($body | ConvertTo-Json)
if ($probe.status -notin @('READY', 'EARLY_READY')) { throw 'Fixture is currently blocked' }
$p = $probe.preview
$body.expected = @{
  history_database_sha256 = $p.history_database_sha256
  features_sha256 = $p.features_sha256
}
# Run the following only after explicit approval and with the authorized localhost process.
$privateToken = [System.Net.NetworkCredential]::new('', (Read-Host 'Operator token' -AsSecureString)).Password
try {
  $result = Invoke-RestMethod "$api/forecasts/publish" -Method Post -ContentType 'application/json' `
    -Headers @{ Authorization = "Bearer $privateToken" } -Body ($body | ConvertTo-Json -Depth 3)
} finally {
  Remove-Variable privateToken
}
```

5. Verify the immutable response by reading `GET /forecasts/{forecast_id}` and the fixture history. Compare canonical fixture, revision number, prior ID, checksum, model, snapshot and cutoff. The ledger independently verifies its record checksum and lineage on read. On disk, a later revision creates a new file; compare the original file SHA-256 before and after a retry or a legitimate update to verify its bytes stayed intact.
6. Reload Prediction History, select the revision and expand **Revision evidence** to see its record, snapshot and feature hashes. Search or filter as needed, then export the filtered CSV. CSV preserves those hashes and comparison IDs and escapes formula-like text. Stop the token-enabled server after the authorized session and return to a read-only launch.

## Revision and authorization evidence

| Case | Validation |
|---|---|
| Newly verified results change a relevant rolling window | A controlled internal Phase 8.5.4 refresh generated V2 with changed features and an immutable V1. |
| Same input against the updated history | NO_CHANGE returned the existing ID. |
| Missing or unrelated lineage | Existing integration rejected an unrelated history; the real service additionally requires child-to-parent hashes and a successor for changed inputs. |
| Stale schedule, unverified live fixture, incomplete statistics or preview hash mismatch | Eligibility retained blocked or unavailable results. The wrong expected snapshot or feature hash failed before append. |
| Unauthorized or cross-origin request | The real read-only server returned HTTP 403. Isolated token-enabled tests also exercised authorization and origin rules. |
| Concurrent writers | Isolated concurrent HTTP and ledger tests exercised exclusive update, retry and immutable record behavior. |

**REAL_V2_NOT_OBSERVED.** This run had an empty real ledger. The real candidate still awaits a manual review, so the populated history, V1/V2 comparison and concurrency evidence come from controlled internal fixtures.
