# Audited recovery study publication exports

The figures show every frozen method and every planned family; all choices are declared in figure-specification.json. These are exact finite-suite descriptions, with no confidence intervals or task-population inference.

The primary operational-safe endpoint uses all planned slots and assigns false to operational failures. Original-SLA, recovery, safety-event, and resource summaries use their displayed observed denominators; unavailable values are explicit. Global-state claim yields use planned denominators, leaving failed slots unavailable rather than labeling them abstentions. Correct definite yield equals definite minus wrong definite; false success is a subset of wrong definite. Report correctness here is judged against audited full-ledger truth; it does not establish contemporaneous evidence support or completed human review. The family heatmap uses paired primary differences within each family and reports the equal-family mean across all 12 families.

CSV files retain original numerators/denominators and reduced exact rational means. Resources and logical simulated decision time are in resources-and-logical-decision-time.csv. Logical decision time is not measured wall latency; the collection duration in the copied summary is not an endpoint. Missing/zero denominators are undefined rather than zero.

Source JSON files have .source.json names so artifact snapshot tools do not reinterpret nested study receipts/manifests. The output manifest binds every rendered figure, table, copied input, and the plotting source. A complete output manifest confirms export completion, not independent visual review of the figures.
