# V2-E Real Vector Memory Acceptance

Status: **VERIFIED**

This is the fresh local-only real embedding regression result. It reuses the existing 50-query / 10-memory benchmark and Qdrant cosine Top-K flow.

Machine-readable evidence: [v2-e-real-embedding-regression.json](raw/v2-e-real-embedding-regression.json).

| Field | Result |
|---|---:|
| Provider host | api.siliconflow.cn |
| Model | Qwen/Qwen3-Embedding-4B |
| Dimension | 2560 |
| Dataset | 50 queries / 10 memories |
| Top-1 | 49/50 (98.00%) |
| Top-3 | 50/50 (100.00%) |
| Threshold | >=46/50 Top-1 |
| Failed queries | query-045; expected memory was recovered in Top-3 |
| Timestamp | 2026-08-27T21:16:56.969892+08:00 |
