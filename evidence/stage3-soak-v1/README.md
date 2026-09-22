# Stage 3 soak report: stage3-soak-v1

Diagnostic only: no thresholds, no gates. Later lanes design
against these numbers.

- Prompt bytes day 1 vs day 30: 64276 vs 42244
- Phase seconds p50/p95: 1.287s / 2.057s over 300 phases
- Fastest-growing table: events (+870 rows from phase 10 to phase 300)
- Recall probe: absent
- Wall seconds: 399.2
