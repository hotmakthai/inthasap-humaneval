"""r4_failure_taxonomy.py — T3: Automatic failure taxonomy from R4 telemetry.

Classifies each unsolved task into failure categories based on telemetry evidence.
Outputs a structured Knowledge Base for analysis.

Usage:
    python r4_failure_taxonomy.py [--state r4_state.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def classify_failure(telemetry: dict, status: str) -> dict:
    """Classify a failed task into a failure category with evidence and confidence.
    
    Returns: {
        "category": str,
        "hypothesis": str,
        "evidence": dict,
        "confidence": str,  # "high", "medium", "low"
        "next_strategy": str,
    }
    """
    if status == "solved":
        return {"category": "solved", "hypothesis": "", "evidence": {}, "confidence": "high", "next_strategy": ""}

    fitness = telemetry.get("best_fitness", 0.0)
    r1_fit = telemetry.get("round1_best_fitness", 0.0)
    r2_fit = telemetry.get("round2_best_fitness", 0.0)
    r3_fit = telemetry.get("round3_best_fitness", 0.0)
    r4_fit = telemetry.get("round4_best_fitness", 0.0)
    trajectory = telemetry.get("fitness_trajectory", [])
    r4_calls = telemetry.get("round4_calls", 0)
    r3_calls = telemetry.get("round3_calls", 0)
    
    # Compute fitness variance across rounds
    round_fitnesses = [f for f in [r1_fit, r2_fit, r3_fit, r4_fit] if f > 0]
    if len(round_fitnesses) >= 2:
        fitness_range = max(round_fitnesses) - min(round_fitnesses)
    else:
        fitness_range = 0.0

    evidence = {
        "best_fitness": fitness,
        "r1_fitness": r1_fit,
        "r2_fitness": r2_fit,
        "r3_fitness": r3_fit,
        "r4_fitness": r4_fit,
        "r3_skipped": r3_calls == 0,
        "r4_attempted": r4_calls > 0,
        "fitness_range_across_rounds": fitness_range,
        "trajectory_points": len(trajectory),
    }

    # Classification rules (hypotheses with evidence)
    
    if fitness < 0.1:
        return {
            "category": "Perception fail",
            "hypothesis": "LLM cannot perceive the pattern — output is almost entirely wrong",
            "evidence": evidence,
            "confidence": "high" if fitness < 0.05 else "medium",
            "next_strategy": "Try different perception hints or manual grid analysis",
        }
    
    if fitness >= 0.9:
        # Check if Round 4 was attempted
        if r4_calls > 0 and r4_fit < 1.0:
            return {
                "category": "Execution fail",
                "hypothesis": "Last-mile execution error — LLM sees pattern but can't fix remaining cells",
                "evidence": evidence,
                "confidence": "high",
                "next_strategy": "More repair attempts or different repair prompt strategy",
            }
        return {
            "category": "Execution fail",
            "hypothesis": "Last-mile execution error — near-perfect but can't close",
            "evidence": evidence,
            "confidence": "high",
            "next_strategy": "Targeted repair (Round 4)",
        }
    
    if fitness_range > 0.3 and len(round_fitnesses) >= 3:
        return {
            "category": "Ambiguity",
            "hypothesis": "Fitness fluctuates wildly across rounds — task may have multiple valid interpretations",
            "evidence": evidence,
            "confidence": "medium",
            "next_strategy": "Analyze if multiple valid outputs exist for training examples",
        }
    
    if 0.3 <= fitness < 0.9:
        # Check if stuck (no improvement across rounds)
        if r2_fit <= r1_fit and (r3_calls == 0 or r3_fit <= r2_fit):
            return {
                "category": "Search fail",
                "hypothesis": "Stuck in local optimum — fitness doesn't improve across rounds",
                "evidence": evidence,
                "confidence": "high",
                "next_strategy": "Strategy rotation or DSL path — try fundamentally different approach",
            }
        return {
            "category": "Search fail",
            "hypothesis": "Partial pattern found but can't improve — search space too narrow",
            "evidence": evidence,
            "confidence": "medium",
            "next_strategy": "Expand strategy pool or hybridize with different candidates",
        }
    
    if 0.1 <= fitness < 0.3:
        return {
            "category": "Rule Induction fail",
            "hypothesis": "LLM found a wrong pattern — output has some structure but fundamentally incorrect",
            "evidence": evidence,
            "confidence": "medium",
            "next_strategy": "Try DSL/program-synthesis path or completely different strategy hint",
        }
    
    return {
        "category": "Unclassified",
        "hypothesis": "Does not fit any category — needs manual inspection",
        "evidence": evidence,
        "confidence": "low",
        "next_strategy": "Manual analysis required",
    }


def build_knowledge_base(state_path: str = "r4_state.json") -> dict:
    """Build failure taxonomy knowledge base from R4 state."""
    state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    results = state.get("results", [])
    
    kb = {}
    category_counts = Counter()
    category_tasks = defaultdict(list)
    
    for r in results:
        tid = r["task_id"]
        status = r["status"]
        telemetry = r.get("telemetry", {})
        
        classification = classify_failure(telemetry, status)
        kb[tid] = {
            "task_id": tid,
            "status": status,
            **classification,
        }
        
        if classification["category"] != "solved":
            category_counts[classification["category"]] += 1
            category_tasks[classification["category"]].append(tid)
    
    total = len(results)
    solved = sum(1 for r in results if r["status"] == "solved")
    failed = total - solved
    
    summary = {
        "total": total,
        "solved": solved,
        "failed": failed,
        "categories": dict(category_counts),
        "category_percentages": {
            cat: f"{count/failed*100:.1f}%" if failed > 0 else "0%"
            for cat, count in category_counts.items()
        },
        "category_examples": {
            cat: tasks[:5]  # up to 5 example task IDs per category
            for cat, tasks in category_tasks.items()
        },
    }
    
    return {"summary": summary, "knowledge_base": kb}


def main():
    state_path = sys.argv[sys.argv.index("--state") + 1] if "--state" in sys.argv else "r4_state.json"
    
    if not Path(state_path).exists():
        print(f"State file not found: {state_path}")
        return
    
    print(f"Building failure taxonomy from {state_path}...")
    result = build_knowledge_base(state_path)
    
    summary = result["summary"]
    print(f"\n=== Failure Taxonomy ===")
    print(f"Total: {summary['total']} | Solved: {summary['solved']} | Failed: {summary['failed']}")
    print(f"\nCategories:")
    for cat, count in sorted(summary["categories"].items(), key=lambda x: -x[1]):
        pct = summary["category_percentages"][cat]
        examples = summary["category_examples"][cat]
        print(f"  {cat:25s} {count:3d} ({pct})  examples: {', '.join(examples[:3])}")
    
    output_path = "r4_failure_taxonomy.json"
    Path(output_path).write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nKnowledge base saved to {output_path}")


if __name__ == "__main__":
    main()
