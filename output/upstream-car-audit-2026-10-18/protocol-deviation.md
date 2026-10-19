# CAR collector deviation: coalesced zero-spend budget refusals

This post-collection finding concerns the 64 native CAR contrastive groups in the cap-4 control. It is a collector diagnostic limitation, not a prospective protocol amendment or a new run.

The pinned native sampler charges a whole K=32 coalition, then launches its 32 coroutine rollouts through `asyncio.gather` (upstream `src/car/attribute/sampling.py:47,51–63`). The adapter records each wrapper refusal (`scripts/run_upstream_car_study.py:370–381`), but its canonical slot advances only on successful scoring (`:337–340,440–459`). Its outer handler invokes `fail_current` once (`:462–469,508–510`). As a result, repeated zero-spend refusals are coalesced under one failed canonical slot.

| Observed shape | Groups | Successful draws | Zero-spend refusals |
| --- | ---: | ---: | ---: |
| One completed stop draw, then 31 initial-decision refusals |40|40|1240|
| One partial refund, a retry refusal, then 31 initial-decision refusals |24|0|768|
| Total |64|40|2008|

The 6,144 planned canonical slots are all retained: 40 known, 64 failed, 6,040 unstarted. Those canonical labels are **not** a one-to-one inventory of actual native starts. Source plus retained refusal records support 2,048 first-coalition coroutine invocations: 40 completed and 2,008 refused, with 4,096 later-coalition invocations unstarted. Individual failed coroutine IDs and their native-slot phase mappings were not retained.

The discrepancy preserves every successful fresh policy reply and all cap-4 totals (three factual plus one continuation call per engine trial). All 64 affected native results are ineligible under the frozen complete-method gate; no eligible numeric estimate is changed. Non-budget semantic checks remain strict. No original receipts, summaries or frozen sources were edited and no trial was rerun.

The separate auditor now admits only the exact two observed failure shapes: index 0 or 1 canonical failed slot, no held decisions, 32 or 31 explicit `CallBudgetExceeded` records with null replies, the specified ordered successful prefix, exact seeds and public-request equality. It retains strict contiguous-decision checks for all known/completed draws.

Exact original compressed examples are copied byte for byte for inspection:
- `diagnostic-examples/00896-upstream_car.json.gz` — SHA-256 `e54166f4868d8502711b45bc3de5087843814b03bcb03148bfcdeb09130ba76e`; original `trials/00896-upstream_car.json.gz`.
- `diagnostic-examples/00900-upstream_car.json.gz` — SHA-256 `50c5bac29abe95c5c79b2c47e2880e892d867d426324db2a3f445598b46d3f0b`; original `trials/00900-upstream_car.json.gz`.

`protocol-deviation.json` binds exact frozen/upstream source ranges, example hashes and full numerical distinctions. `decision-index-investigation.json` retains every affected raw decision list.
