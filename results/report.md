# SelfGuard v3 smart routing: sealed SEP result

Sealed SHA-256 `f2a8adbec7ccc9c98b5cb485504b91b37eb0e0d8eb2d83d2ffd0278b95a90fc8`, n = 600.

| Metric | Standard | Watchword (displaced always) | **Smart routing** |
|---|---:|---:|---:|
| Attack success (residual) | 62.2% raw | 10.2% | **10.2%** |
| Clean grounding | 82.7% | 72.2% | **80.0%** |
| Clean replies withheld | - | 0.8% | **0.8%** (Wilson hi 1.9%) |
| Legit instruction followed | 77.0% | - | 77.2% |

McNemar b=323 c=11 p=7.24e-81. Finder flagged 12.7% of clean and 100.0% of attacked data.

- 1_protection: **PASS**
- 2_quality: **PASS**
- 3_false_alarms: **PASS**

Overall: **PASS**
