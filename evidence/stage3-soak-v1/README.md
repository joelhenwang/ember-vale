# Stage 3 soak report: stage3-soak-v1

Diagnostic only: no thresholds, no gates. Later lanes design
against these numbers.

- Prompt bytes day 1 vs day 30: 64406 vs 42480
- Phase seconds p50/p95: 2.433s / 3.732s over 300 phases
- Fastest-growing table: events (+870 rows from phase 10 to phase 300)
- Recall probe: absent
- Wall seconds: 778.9
