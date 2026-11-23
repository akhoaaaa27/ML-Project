# FRG-02 — Official schedule and freshness evidence

**PASS at the actual verification time.** V3 schedule evidence was still valid at `2026-11-23T06:12:24.075811Z`. It was acquired `2026-11-21T20:20:23.160077Z`, with expiry `2026-11-23T20:20:23.160077Z` inclusive. Levante–Elche was genuinely upcoming until its own earlier cutoff at kickoff, `2026-11-23T20:00:00Z`.

| Status in 2026/27 catalogue | Count at verification |
|---|---:|
| READY | 1 |
| EARLY_READY | 6 |
| WAITING_DATA | 245 |
| UNAVAILABLE | 128 |
| Total | 380 |

All 252 upcoming catalogue entries had recent provider evidence. WAITING_DATA comprised 154 `REGISTRY_COVERAGE_UNVERIFIED` and 91 `MISSING_ROLLING_STATISTICS`. UNAVAILABLE comprised 128 `TARGET_NOT_UPCOMING`. Registry identity conflicts were zero. Recent schedule evidence is one input to eligibility and cannot fill missing history. The acquisition hash below ties this evidence to the existing V3 input, and V3's registry verification on those examples was `2026-11-21T21:33:38.619530Z`.

| Fixture and provider ID | V3 and newly retrieved provider kickoff | Observed official LaLiga kickoff, UTC | Original confirmation |
|---|---|---|---|
| `research:laliga:2026:Levante:Elche` · 19732618 | `2026-11-23T20:00:00Z` | Same, shown as 21:00 CET in Spain. Scheduled, with no postponement or rescheduling shown. | 21 October 2026. [Official match](https://www.laliga.com/partido/temporada-2026-2027-laliga-ea-sports-levante-ud-elche-cf-13) · [Official matchday 13 announcement](https://www.laliga.com/noticias/horarios-de-la-decimotercera-jornada-de-laliga-ea-sports-2026-27) |
| `research:laliga:2026:Levante:Racing Santander` · 19732607 | `2026-11-27T20:00:00Z` | Same, also shown as 21:00 CET in Spain. Scheduled. It remained WAITING_DATA for registry coverage. | 6 November 2026. [Official match](https://www.laliga.com/en-GB/match/temporada-2026-2027-laliga-ea-sports-levante-ud-r-racing-club-14) · [Official matchday 14 announcement](https://www.laliga.com/noticias/horarios-de-la-decimocuarta-jornada-de-laliga-ea-sports-2026-27) |

The six internal EARLY_READY candidates had provider kickoff `00:00:00Z`. Official club calendars independently display dates with kickoff time blank for these fixtures. They are date-matched but exact kickoff is unconfirmed. Exclude them when choosing a prospective defense demonstration until the league publishes their times. The trusted engine's existing provider-based eligibility counters are preserved. [Official Levante calendar](https://www.laliga.com/clubes/levante-ud/proximos-partidos) · [Official Athletic calendar](https://www.laliga.com/clubes/athletic-club/proximos-partidos) · [Official Elche calendar](https://www.laliga.com/es-US/clubes/elche-c-f/proximos-partidos) · [Official season calendar](https://www.laliga.com/calendar-2026-2027/laliga-easports)

| Public source | Retrieval UTC | SHA-256 of captured bytes |
|---|---|---|
| Official Levante–Elche match | `2026-11-23T06:09:15.824985Z` | `8182cc3ee51ed7d352b6c7064312b26d464b969be87b00077d3352ee78df77e5` |
| Official Levante–Racing match | `2026-11-23T06:09:19.458077Z` | `508d977920f5e7c3d8c2f28ce61ab1834f6a27afaa048a9bf52e27f20cc541ca` |
| Official Levante calendar | `2026-11-23T06:09:21.549702Z` | `edf03771fea672239d6b1c340d49f9746e22495e96df6eb243a6703ef269a1fa` |
| Pinned V3 CSV | `2026-11-21T20:20:23.160077Z` | `dbbd9d99526717a03af3548375340aaa7364c4699a0689bf9e0d1a6421cd3c0e` |
| Current public CSV | `2026-11-23T06:09:26.723643Z` | `9ba0715cf23c49d493550655fd82fe0039c9f26a512f40d3cdfb54abffe131e0` |

The match pages did not provide a fixture-specific update timestamp. The latest public Sportmonks/xGTables export is byte-identical to the prepared candidate source, with HTTP Last-Modified `2026-11-22T23:19:37Z`. It leaves both schedule rows unchanged. The corroboration is recent as an observation, while the dated official confirmations are older than the active 48-hour window. The trusted snapshot derives its schedule age from the attested V3 CSV. [Public xGTables export](https://www.xgtables.io/data/la-liga/2026/)

## Re-attestation decision

**BLOCKED for renewal.** Current Phase 8.5.4 preserves unchanged schedule rows and cannot independently record a newer reaffirmation without evidence from a fixture-specific confirmed schedule item. We found no new official publication or versioned fixture timestamp for the checked kickoff pairs. Redownloading a known CSV or refreshing a rendered match page is insufficient to justify a new clock, so the FRG implementation keeps the existing eligibility policy.

A future controlled extension would require a dated league release or versioned authoritative reaffirmation that explicitly binds the season, fixture and provider/league IDs, teams, UTC kickoff, source URL, issuer timestamp and captured SHA-256. It would preserve the previous observation, require an explicit receipt for that exact record and go through validated immutable publication. Self-issued timestamps, duplicate observations, absent or expired evidence and identity or kickoff disagreements should fail review. No such evidence enters V3 in this gate.

A read-only offline evaluation at one microsecond past V3 expiry returned 251 `WAITING_DATA/FIXTURE_FRESHNESS_UNVERIFIED` and 129 `UNAVAILABLE`, including the Levante–Elche `TARGET_ALREADY_STARTED` result. READY and EARLY_READY were zero at that counterfactual clock. This negative check did not alter the server clock or any SQLite files. See the [actual real preview](PHASE_9_FRG_03_REAL_FORECAST_EVIDENCE.md).
