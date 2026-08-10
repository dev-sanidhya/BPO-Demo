# HarperValleyBank evidence subset

This directory contains four unmodified, human-recorded two-party calls selected
from the Stanford/Gridspace HarperValleyBank corpus. The calls are simulated
banking interactions performed by human speakers; they are not production
customer calls. Aperture CX uses this subset to exercise real WebRTC media,
speaker-separated transcription, live guidance, QA, reporting, and playback
without inventing customer evidence.

Source: https://github.com/cricketclub/gridspace-stanford-harper-valley

Paper: https://arxiv.org/abs/2010.13929

License: Creative Commons Attribution 4.0. The complete supplied license is in
`LICENSE-CC-BY-4.0.txt`. The audio, source metadata, and source transcripts are
copied without modification. Any derived Aperture transcript, score, summary,
cost, or rating normalization must be labelled as derived rather than source
ground truth.

| SID | Published task | Published caller partner rating | Published labels (script/caller MOS/agent MOS) |
| --- | --- | ---: | --- |
| `eb82ec7b5f0944ca` | Check balance | 10/10 | 5/5/5 |
| `ff0296d00e5e4184` | Get branch hours | 10/10 | 5/5/5 |
| `3a20358e1bfc4a17` | Replace card | 7/10 | 4/4/4 |
| `a7ccc3379af44b9f` | Schedule appointment | 3/10 | 4/5/4 |

The published `partner_rating` is not CSAT. The platform must never display it
as a customer CSAT response. If it is normalized for a chart, the transformation
and original 10-point value must remain visible.
