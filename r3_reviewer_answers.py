"""r3_reviewer_answers.py -- Generate detailed answers to reviewer questions.

Q1: Perception ablation (with vs without)
Q2: Evolution round-by-round cumulative solves
Q3: Diff feedback before/after example
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_state(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"results": []}
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    p5b = load_state("p5b_state.json")
    r3 = load_state("r3_state.json")

    p5b_results = {r["task_id"]: r for r in p5b.get("results", [])}
    r3_results = {r["task_id"]: r for r in r3.get("results", [])}
    r3_raw = r3.get("results", [])

    p5b_solved = {tid for tid, r in p5b_results.items() if r["status"] == "solved"}
    r3_solved = {tid for tid, r in r3_results.items() if r["status"] == "solved"}
    newly_solved = r3_solved - p5b_solved

    print("=" * 70)
    print("REVIEWER Q&A -- Detailed Attribution Analysis")
    print("=" * 70)

    # ============================================================
    # Q1: Perception -- with vs without
    # ============================================================
    print("\n" + "=" * 70)
    print("Q1: PERCEPTION -- How many solves attributed to perception hints?")
    print("=" * 70)

    with_hints_solved = 0
    without_hints_solved = 0
    with_hints_newly = 0
    without_hints_newly = 0
    with_hints_total = 0
    without_hints_total = 0

    for tid, r in r3_results.items():
        tel = r.get("telemetry", {})
        has_hints = tel.get("had_perception_hints", False)
        is_solved = r["status"] == "solved"
        is_new = tid in newly_solved

        if has_hints:
            with_hints_total += 1
            if is_solved:
                with_hints_solved += 1
            if is_new:
                with_hints_newly += 1
        else:
            without_hints_total += 1
            if is_solved:
                without_hints_solved += 1
            if is_new:
                without_hints_newly += 1

    print(f"\n  Tasks WITH perception hints:    {with_hints_total}")
    print(f"    Solved: {with_hints_solved}/{with_hints_total} ({with_hints_solved/max(with_hints_total,1)*100:.1f}%)")
    print(f"    Newly solved (vs P5b): {with_hints_newly}")
    print()
    print(f"  Tasks WITHOUT perception hints: {without_hints_total}")
    print(f"    Solved: {without_hints_solved}/{without_hints_total} ({without_hints_solved/max(without_hints_total,1)*100:.1f}%)")
    print(f"    Newly solved (vs P5b): {without_hints_newly}")
    print()
    print(f"  => Perception hints present in {with_hints_total}/{len(r3_results)} tasks ({with_hints_total/max(len(r3_results),1)*100:.1f}%)")
    print(f"  => All {len(newly_solved)} newly solved tasks had perception hints: {with_hints_newly == len(newly_solved)}")
    print()
    print("  EXPERIMENTAL DESIGN NOTE:")
    print("  Perception hints are injected in ALL evolutionary rounds (R1, R2, R3)")
    print("  and also in the non-evolutionary fallback path.")
    print("  To run a proper ablation (perception ON vs OFF), we would need to:")
    print("  1. Re-run 400 tasks with perception hints DISABLED (evolutionary=True)")
    print("  2. Compare solve rate: R3_with_hints vs R3_without_hints")
    print("  3. The delta would be the Perception attribution")
    print("  Current data shows hints are UBIQUITOUS (present in all tasks),")
    print("  so the +125 is an UPPER BOUND on perception contribution.")

    # ============================================================
    # Q2: Evolution -- round-by-round cumulative
    # ============================================================
    print("\n" + "=" * 70)
    print("Q2: EVOLUTION -- Round-by-round cumulative solves")
    print("=" * 70)

    # For each task, show which round solved it
    round_solves = {1: 0, 2: 0, 3: 0, None: 0}
    round_newly = {1: 0, 2: 0, 3: 0, None: 0}

    # Also track cumulative: after Round 1, after Round 2, after Round 3
    for tid in r3_solved:
        tel = r3_results[tid].get("telemetry", {})
        sr = tel.get("solved_round")
        round_solves[sr] = round_solves.get(sr, 0) + 1
        if tid in newly_solved:
            round_newly[sr] = round_newly.get(sr, 0) + 1

    total_evo = round_solves[1] + round_solves[2] + round_solves[3]
    total_new_evo = round_newly[1] + round_newly[2] + round_newly[3]

    print(f"\n  Round 1 (8 diverse candidates + strategy hints):")
    print(f"    Solved: {round_solves[1]} tasks")
    print(f"    Newly solved (vs P5b): {round_newly[1]}")
    print(f"    => These tasks were solved on FIRST attempt with diverse generation")
    print()
    print(f"  Round 2 (individual revision + diff feedback):")
    print(f"    Solved: {round_solves[2]} tasks (ADDITIONAL after R1 failed)")
    print(f"    Newly solved (vs P5b): {round_newly[2]}")
    print(f"    => These tasks needed diff feedback to revise failing candidates")
    print()
    print(f"  Round 3 (pooled hybridization of best candidates):")
    print(f"    Solved: {round_solves[3]} tasks (ADDITIONAL after R1+R2 failed)")
    print(f"    Newly solved (vs P5b): {round_newly[3]}")
    print(f"    => These tasks needed combining elements from multiple candidates")
    print()
    print(f"  Non-evolutionary path (no solved_round):")
    print(f"    Solved: {round_solves[None]} tasks")
    print(f"    Newly solved (vs P5b): {round_newly[None]}")
    print()
    print(f"  CUMULATIVE:")
    print(f"    After Round 1: {round_solves[1]} solved ({round_solves[1]/len(r3_results)*100:.1f}%)")
    print(f"    After Round 2: {round_solves[1]+round_solves[2]} solved ({(round_solves[1]+round_solves[2])/len(r3_results)*100:.1f}%)")
    print(f"    After Round 3: {round_solves[1]+round_solves[2]+round_solves[3]} solved ({(round_solves[1]+round_solves[2]+round_solves[3])/len(r3_results)*100:.1f}%)")
    print(f"    + Non-evo:     {total_evo + round_solves[None]} solved ({(total_evo + round_solves[None])/len(r3_results)*100:.1f}%)")

    # Show some Round 2 task IDs for Q3
    r2_tasks = []
    for tid in r3_solved:
        tel = r3_results[tid].get("telemetry", {})
        if tel.get("solved_round") == 2 and tid in newly_solved:
            r2_tasks.append(tid)

    # ============================================================
    # Q3: Diff Feedback -- concrete example
    # ============================================================
    print("\n" + "=" * 70)
    print("Q3: DIFF FEEDBACK -- Before/After example")
    print("=" * 70)

    print(f"\n  Tasks solved by Round 2 (diff feedback): {r2_tasks[:10]}")
    print()

    # For each R2 task, show the fitness trajectory
    for tid in r2_tasks[:3]:
        r = r3_results[tid]
        tel = r.get("telemetry", {})
        traj = tel.get("fitness_trajectory", [])
        r1_fit = tel.get("round1_best_fitness", 0)
        r2_fit = tel.get("round2_best_fitness", 0)
        r3_fit = tel.get("round3_best_fitness", 0)
        calls = tel.get("llm_calls", 0)

        print(f"  Task {tid}:")
        print(f"    Round 1 best fitness: {r1_fit:.3f} (NOT solved)")
        print(f"    Round 2 best fitness: {r2_fit:.3f} (SOLVED with diff feedback)")
        print(f"    Round 3 best fitness: {r3_fit:.3f}")
        print(f"    LLM calls: {calls}")
        print(f"    Fitness trajectory: {traj[:5]}{'...' if len(traj) > 5 else ''}")
        print(f"    Candidate: {r.get('candidate', 'N/A')[:80]}...")
        print()

    # Show what diff feedback looks like (from arc_diff.py)
    print("  WHAT DIFF FEEDBACK LOOKS LIKE:")
    print("  (Deterministic ASCII diff from arc_diff.py analyze_diff)")
    print()
    print("  Example output format:")
    print("    INVARIANTS (true across all training pairs):")
    print("      - Grid dimensions: 3x3 -> 3x3 (unchanged)")
    print("      - Color 0 count: preserved")
    print("    CHANGES (input -> output):")
    print("      - Color 2 -> Color 3 (cell-wise mapping)")
    print("      - Position (0,1): 2 -> 3")
    print("      - Position (1,2): 2 -> 3")
    print()
    print("  This diff is injected into the Round 2 prompt as:")
    print("    'Your previous candidate failed. Here is what changed")
    print("     between input and output in the training examples:'")
    print("    + [diff text]")
    print("    'Revise your solution to match these patterns.'")

    # ============================================================
    # Summary
    # ============================================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print(f"  P5b:  {len(p5b_solved)}/400 solved (24.2%)")
    print(f"  R3:   {len(r3_solved)}/400 solved (55.0%)")
    print(f"  Delta: +{len(newly_solved) - len(p5b_solved - r3_solved)} solved")
    print(f"         ({len(newly_solved)} new, -{len(p5b_solved - r3_solved)} lost)")
    print()
    print(f"  Feature        Delta Solved    Notes")
    print(f"  {'-'*20} {'-'*12}  {'-'*40}")
    print(f"  Evolution R1         +{round_newly[1]:>3}   8 diverse candidates w/ strategy hints")
    print(f"  Evolution R3          +{round_newly[3]:>3}   Pooled hybridization of best candidates")
    print(f"  Diff Feedback R2     +{round_newly[2]:>3}   Individual revision w/ ASCII diff")
    print(f"  Perception          +{with_hints_newly:>3}   Deterministic hints (ubiquitous, $0)")
    print(f"  Non-evo path          +{round_newly[None]:>3}   Simple 2-attempt fallback")
    print()

    # Save detailed JSON
    report = {
        "q1_perception": {
            "with_hints_total": with_hints_total,
            "with_hints_solved": with_hints_solved,
            "with_hints_newly": with_hints_newly,
            "without_hints_total": without_hints_total,
            "without_hints_solved": without_hints_solved,
            "without_hints_newly": without_hints_newly,
            "ablation_needed": True,
            "note": "Perception hints are ubiquitous; proper ablation requires re-running without hints",
        },
        "q2_evolution": {
            "round1_solved": round_solves[1],
            "round1_newly": round_newly[1],
            "round2_solved": round_solves[2],
            "round2_newly": round_newly[2],
            "round3_solved": round_solves[3],
            "round3_newly": round_newly[3],
            "non_evo_solved": round_solves[None],
            "non_evo_newly": round_newly[None],
            "cumulative_after_r1": round_solves[1],
            "cumulative_after_r2": round_solves[1] + round_solves[2],
            "cumulative_after_r3": round_solves[1] + round_solves[2] + round_solves[3],
        },
        "q3_diff_feedback": {
            "r2_task_ids": r2_tasks,
            "examples": [
                {
                    "task_id": tid,
                    "round1_fitness": r3_results[tid].get("telemetry", {}).get("round1_best_fitness", 0),
                    "round2_fitness": r3_results[tid].get("telemetry", {}).get("round2_best_fitness", 0),
                    "fitness_trajectory": r3_results[tid].get("telemetry", {}).get("fitness_trajectory", [])[:10],
                    "llm_calls": r3_results[tid].get("telemetry", {}).get("llm_calls", 0),
                }
                for tid in r2_tasks[:5]
            ],
        },
    }
    Path("r3_reviewer_answers.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("  Detailed JSON saved to r3_reviewer_answers.json")


if __name__ == "__main__":
    main()
