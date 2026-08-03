# E1-R2 Communication Metric Note

Generated: 2026-08-03T11:42:59.137301+00:00

The formal E1-R2 runs record **communication as an update count**, not bytes.

- Stored field: `total_communication`
- Semantic: **number_of_received_client_updates**
- Paper label: **Number of received client updates**

Do **not** describe this metric as communication bytes unless a separate serialized-byte counter with evidence is introduced.

Audit status: **PASS** over 25 formal runs.
