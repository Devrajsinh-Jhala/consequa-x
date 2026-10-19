# Blinded evidence review packet

Open `index.html` in a browser; it works offline and makes no network requests.
Read `rubric.md`, then fill a separate copy of `blank_annotations.csv` for each
independent reviewer. Use a spreadsheet editor or a text editor and preserve
the CSV column names. Each of the 84 renamed cards has a corresponding JSON
file in `cases/`. Labels and reviewer identifiers are deliberately blank.

Allowed labels:

| CSV field | Values |
| --- | --- |
| state | satisfied, violated, unknown |
| action_linked | satisfied, not_satisfied, unknown |
| origin | confirmed, other_actor, unknown |

The optional `support` field may cite the visible evidence; `note` may explain
an ambiguity. Each reviewer should label all cards independently before seeing
another reviewer's labels. Keep original independent files and any later
adjudication separately. Follow the full instructions in `rubric.md`.

No expected answers or automatic predictions are supplied. The packet is ready
for human annotation; it is **not evidence that human validation has occurred**.
Repeated cards are not independent tasks. Identifiers are meaningful only within
a card. `manifest.json` lists shareable file hashes for checking unchanged bytes;
it does not authenticate evidence or establish correctness.

Share this ZIP or its extracted contents. The creator's private mapping and
source inventory are kept outside this packet and must not be given to blinded
reviewers before independent labels are locked.
