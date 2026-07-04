# Inthasap Council Trinity — HumanEval Benchmark Results

**Creator:** Wichat Inthasap (หลวงพ่อวิชาติ อินทรัพย์)  
**Organization:** Inthasap Guard · บ้านอินทรัพย์ · Thailand  
**Date:** July 4, 2026  

## Overview

This repository contains the official HumanEval benchmark results for **Inthasap Council Trinity**, a multi-agent orchestration system built by a single independent developer that enhances LLM code generation through structured deliberation and reasoning architecture.

> **Note**: The orchestration architecture (agent personas, routing logic, and deliberation protocols) is proprietary and **not included** in this repository. Only the benchmark results and generated code samples are shared for verification and reproducibility of the reported scores.

## Results (Final — Round 3)

| Mode | Pass@1 | Score |
|------|--------|-------|
| Raw LLM (DeepSeek V4 baseline) | 132/164 | **80.5%** |
| **Scaffolded (Council Trinity)** | **157/164** | **95.7%** |
| **Architecture Boost** | **+25 problems** | **+15.2pp** |

### Comparison with Frontier Models (HumanEval Pass@1)

| Model | Pass@1 | vs Council Trinity |
|-------|--------|--------------------|
| GPT-4 (2023) | 67.0% | **+28.7%** |
| GPT-4 Turbo | 85.0% | **+10.7%** |
| GPT-4o | 90.0% | **+5.7%** |
| Claude 3.5 Sonnet | ~92.0% | **+3.7%** |
| Claude 3.7 Sonnet | ~93.0% | **+2.7%** |
| **🏠 Inthasap Council Trinity (Scaffolded)** | **95.7%** | — |
| o3 / GPT-5 class | ~96.0% | -0.3% |

## Files

| File | Description |
|------|-------------|
| `samples_raw.jsonl` | Raw LLM completions in OpenAI HumanEval format |
| `samples_scaffolded.jsonl` | Scaffolded completions in OpenAI HumanEval format |
| `submission_summary.json` | Summary with pass@1 scores |
| `bench_humaneval_results.json` | Full per-problem results (pass/fail + errors) |
| `bench_dashboard.html` | Interactive dashboard with charts and tables |

## Verification

To verify the results using the official OpenAI HumanEval harness:

```bash
# Install the official HumanEval evaluation framework
pip install human-eval

# IMPORTANT: Uncomment the execution code in human_eval/execution.py
# (The execution is deliberately disabled for safety — read the disclaimer)

# Run verification
evaluate_functional_correctness samples_scaffolded.jsonl
```

Expected output:
```
{'pass@1': 0.957}
```

## Format

Each `.jsonl` file contains one JSON object per line in the standard OpenAI format:

```json
{"task_id": "HumanEval/0", "completion": "def has_close_elements(elements, threshold):\n    ..."}
```

- `task_id`: The HumanEval problem identifier
- `completion`: The generated code (function body only, without the prompt)

## Benchmark Details

- **Dataset**: OpenAI HumanEval (164 hand-written Python programming problems)
- **Source**: https://github.com/openai/human-eval
- **Evaluation**: Each problem's generated code is executed against the official test suite
- **Metric**: pass@1 (single attempt, no majority voting)
- **Date**: July 2026

## About Inthasap Council Trinity

Inthasap Council Trinity is a scaffolding system that orchestrates multiple AI agents to collaboratively solve coding problems. The system uses a structured deliberation protocol where agents discuss, review, and refine solutions before producing a final answer.

The "Raw" mode represents the base LLM generating code directly. The "Scaffolded" mode represents the same LLM enhanced by the Council Trinity orchestration system.

**The +15.2% improvement (80.5% → 95.7%) demonstrates the value of structured multi-agent deliberation and reasoning architecture for code generation tasks.**

This result was achieved by a single independent developer (not a research lab or organization) using a cost-efficient base model (DeepSeek V4, ~1/10 cost of GPT-4o), proving that **reasoning architecture matters more than model size**.

## Citation

If you reference these results, please cite:

```bibtex
@misc{inthasap_council_trinity_2026,
  title={Inthasap Council Trinity: Multi-Agent Scaffolding Achieves 95.7\% on HumanEval},
  author={Wichat Inthasap},
  organization={Inthasap Guard, Thailand},
  year={2026},
  url={https://github.com/inthasap/humaneval-results}
}
```

## License

- **Benchmark results and generated code**: MIT License
- **HumanEval dataset**: MIT License (© OpenAI)
- **Council Trinity architecture**: Proprietary (not included)
