# FRG-01 — Refresh candidate review dossier

**REVIEW_BLOCKED · INSUFFICIENT_EVIDENCE.** The existing `phase96-20261123-candidate` reproduced successfully from its recorded inputs. Independent sources confirm the match and score. No independent source checked establishes that Sportmonks revised Athletic Club's total xG from 1.7853 to 1.8981 or explains the revision.

## Candidate and review scope

| Item | Observed evidence |
|---|---|
| Parent binding | `phase853_v3_20261122`, DB SHA-256 `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |
| Candidate semantic content SHA-256 | `f5015681cbef5d572fd336ddde040bc09fadabf8e6eebc3e69abaecfb8192c1e` |
| Candidate effect SHA-256 | `5152fb6f03b03565021a3203d80995a4d80ed4bf6bb1b03153fa8a219f39db87` |
| Manual change ID | `775e7c6e43a38401f4764f27e1d4680739553d6971ccbde66d8313a8d500d1ec` |
| Recomputed outcome | `PREPARED` and `REVIEW_REQUIRED`; eight automatic changes, one manual change, one remaining pending-statistics fixture, zero conflicts and zero schedule changes |
| Original acquisition manifest SHA-256 | `d4bc7cba23d9048fc3d562dde8b8f50bb3f68fa7651ea51d5b2f2ae39089a348` |
| Candidate acquisition manifest SHA-256 | `6cce5a110195c33601b55cc44c7979dd14b640c4e62c70c361c48a3f3dfaade9` |
| Candidate independent completion input SHA-256 | `d3985d80441546d483ef29bc624998287553b0b054cfef9af2c6891952712051` |

The five automatic completions were Osasuna–Málaga, Getafe–Atlético Madrid, Racing Santander–Real Sociedad, Real Madrid–Celta Vigo and Barcelona–Villarreal. The three automatic pending-statistics resolutions were Alavés–Deportivo, Rayo Vallecano–Valencia and Sevilla–Real Betis. The private candidate and report retain their exact change IDs and source lineage.

## Athletic Club–Espanyol

Canonical key `research:laliga:2026:Athletic Club:Espanyol`, Sportmonks ID `19732621`, LaLiga 2026/27 matchday 13, San Mamés, `2026-11-20T20:00:00Z`. Home Athletic Club, away Espanyol, final score 0–1. Both snapshots describe a verified completed match with complete statistics. [Official LaLiga match](https://iaas-public-front-pro.laliga.com/en-US/match/temporada-2026-2027-laliga-ea-sports-athletic-club-rcd-espanyol-de-barcelona-13) · [Athletic Club match report](https://www.athletic-club.eus/en/teams/athletic-club/2026-27/liga/matches/athletic-club-vs-rcd-espanyol/1_8584/)

| Metric | Athletic Club old → proposed | Espanyol old → proposed |
|---|---:|---:|
| Goals for / against | 0 / 1 → 0 / 1 | 1 / 0 → 1 / 0 |
| Shots / on target | 17 / 6 → 17 / 6 | 6 / 3 → 6 / 3 |
| Total xG | **1.7853 → 1.8981** | 0.6960 → 0.6960 |
| Total xGA | 0.6960 → 0.6960 | **1.7853 → 1.8981** |

Both xG and shot counts are attributed to Sportmonks through xGTables. Sportmonks defines team total xG as the sum of modeled scoring probabilities across shots, distinct from xG on target. V3 labels reported shots as having unverified penalty inclusion. The candidate's mixed-provider label does not establish equivalence to the FBref training definitions. The reciprocal xGA change reflects the same Athletic total xG update. [Sportmonks xG definitions](https://www.sportmonks.com/football-api/xg-data/) · [xGTables source disclosure](https://www.xgtables.io/sources/)

| Export from the same publisher | Acquisition UTC | Published HTTP Last-Modified UTC | CSV SHA-256 |
|---|---|---|---|
| V3 | `2026-11-21T20:20:23.160077Z` | `2026-11-21T13:35:35Z` | `dbbd9d99526717a03af3548375340aaa7364c4699a0689bf9e0d1a6421cd3c0e` |
| Candidate | `2026-11-23T05:39:18.010085Z` | `2026-11-22T23:19:37Z` | `9ba0715cf23c49d493550655fd82fe0039c9f26a512f40d3cdfb54abffe131e0` |
| FRG re-download from xGTables | `2026-11-23T06:09:26.723643Z` | `2026-11-22T23:19:37Z` | Same bytes as candidate |

The later retrieval confirms what xGTables currently distributes. Candidate historical match verification retains the parent verification at `2026-11-21T21:33:38.619530Z`; the statistical payload has its own newer acquisition. Official LaLiga corroborates the fixture, final score and 17–6 total shots. Its captured match page provides no Sportmonks xG correction or revision record. Its capture time is `2026-11-23T06:09:13.039134Z`, SHA-256 `201d9e4891cfdb45ac805df882524de8af822ca869073963a87cfb7fa338758d`. FotMob reports Opta-powered xG of 1.45 and 0.53 for the same match. That is evidence of a different published xG estimate and does not adjudicate between the two Sportmonks versions. [LaLiga match statistics](https://iaas-public-front-pro.laliga.com/en-US/match/temporada-2026-2027-laliga-ea-sports-athletic-club-rcd-espanyol-de-barcelona-13) · [FotMob match statistics and attribution](https://www.fotmob.com/es/matches/athletic-club-vs-espanyol/2crecr) · [Public xGTables export](https://www.xgtables.io/data/la-liga/2026/)

## Impact and operator decision

Only a rolling window containing the affected historical row can carry the correction. A read-only feature comparison substituted the single proposed field pair in memory at the same `2026-11-23` cutoff. The Athletic Club and opponent xG features move by +0.02256 in the Athletic Club–Levante example, and Espanyol and opponent xGA by +0.02256 in the Levante–Espanyol example. Levante–Elche has identical features because neither window includes the match. The comparison did not use the complete successor candidate and did not create a snapshot or prospective forecast for the sample future fixtures.

The operator can request a dated Sportmonks change record or a versioned fixture `19732621` export confirming the 1.8981 figure, model/metric identity and unchanged away total, or a reproducible matching same-model event reconciliation. Record the exact evidence URL, timestamp and SHA-256, then reassess the same immutable change. Until then leave `reviews.json` empty. `INSUFFICIENT_EVIDENCE` is a dossier recommendation. The formal CLI takes an explicit `APPROVE` or `REJECT` only after authorization. Any separately prepared alternative proposal needs its own immutable candidate ID and review. [Defense runbook](PHASE_9_DEFENSE_RUNBOOK.md#operator-decisions)
