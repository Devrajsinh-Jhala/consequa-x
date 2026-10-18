# Closed matched-study audit, 18 October 2026

Read-only computational checks by a separate AI agent, plus inspection of both figure PNGs. This is not independent human validation. No generation, data repair or primary-analyzer rerun was performed.

Collection closed normally at 17:30 IST after about 4 h 58 min, before its six-hour cutoff: **503 completed + 1 retained failed / 504 planned**, no partial or unstarted slots. There were **896/1,512 attempted chat calls**, 896 received and zero transport failures. Slot 109 (Llama, profile v2, desk missing-provenance) failed strict JSON parsing; it was not regenerated.

All **4,317 raw**, **7 analysis** and **15 figure** inventory entries match their recorded hashes. All **45 frozen/current source bindings** match, covering 43 unique current repository paths. The **2,803-event journal hash chain** is valid and ends with `run_stopped`; there is no runner lock. All 15 auditor/target summary fractions were independently recounted from the analysis rows with no mismatch.

| Auditor | State correct / assessable; wrong / claims | Action-linked correct / assessable; wrong / claims | Origin correct / assessable; wrong / claims |
| --- | --- | --- | --- |
| Public response | 148/503; 53/201 | 148/503; 53/201 | 0/310; undefined (0/0) |
| Agent assessment | 104/503; 148/252 | 116/503; 136/252 | 0/310; undefined (0/0) |
| Readback only | 431/503; 0/431 | 0/503; undefined (0/0) | 0/310; undefined (0/0) |
| Independent public reference | 431/503; 0/431 | 385/503; 0/385 | 216/310; 0/216 |
| Consequa-X | 431/503; 0/431 | 385/503; 0/385 | 216/310; 0/216 |

The independent reference and Consequa-X give **identical full prediction dictionaries in all 503 completed episodes**, including origin and abstentions. This supports an implementation consistency claim, not superiority over the same-information reference.

Origin gold is assessable in 310 completed episodes: 238 confirmed origins and 72 other-actor origins. The 193 unknown-origin gold cases are excluded only from the origin semantic denominator. These 310 are not all state successes: five excess matching-effect cases retain known origin but violate the exact-count state contract. Emitted origin claims are 144 confirmed +72 other-actor =216. The 94 assessable-origin abstentions comprise 48 delayed-readback and 46 missing-public-provenance cases. State abstentions are 72 delayed-readback cases. Action-linked abstentions are 72 lag +46 omitted provenance =118. Zero-denominator claim error remains undefined; abstention is not correct. Full-planned correct yield is separately **431/504 state, 385/504 action-linked, 216/504 origin**.

Gemma dispatches **0/168** times; Llama dispatches **166/167** completed episodes (168 planned), and Qwen **168/168**. Overall dispatch is **334/503 completed** or **334/504 planned**; all 58 retries occur in Qwen. An empty-ledger correct negative does not demonstrate execution or dispatched fault handling. Of 288 scheduled nonclean-provider episodes, 192 actually exercise a nonclean provider fault; 96 completed episodes do not dispatch one. Origin omission is configured in72 planned cases and materializes in46 completed cases.

The 504 slots cover three models, two profiles, fourteen fixed case cells and six seed-controlled repetitions. The case cells comprise two wording families and seven already exposed mechanisms. They are not 504 independent tasks, and do not establish generalization to unseen mechanisms. Family and size are confounded; all models are small quantized local models. No causal attribution, faithful named-system reproduction, statistical superiority, human rationale validation or conference acceptance is established. Execution diagnostics were added after collection began and are explicitly descriptive; the frozen primary source and protocol are unchanged.

Both figure PNGs were visually inspected. Their inventory binds vector exports, exact input copies and fraction tables. Manual paper integration and final page-layout verification remain separate work.
