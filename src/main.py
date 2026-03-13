"""
CLI entrypoint for the Plan-Build-Inspect loop.

Usage:
    python -m src.main "Create a house with plants"
"""

import sys

from src.loops.plan_build_inspect import plan_build_inspect


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        raise SystemExit('Usage: python -m src.main "<prompt>"')

    prompt = " ".join(argv)
    result = plan_build_inspect(prompt)

    plan = result["plan"]
    verification = result["verification"]
    exec_result = result["execution"]
    inspection = result["inspection"]

    print("=== Plan-Build-Inspect Result ===")
    print(f"Prompt: {prompt}")
    print(f"Plan: {plan.name} ({len(plan.components)} components)")
    print(f"Description: {plan.description}")
    print()

    # Show components
    print("--- Components ---")
    for comp in plan.components:
        mat_info = ""
        if comp.material:
            c = comp.material.color
            mat_info = f" color=({c[0]:.1f},{c[1]:.1f},{c[2]:.1f})"
        print(f"  {comp.name}: {comp.primitive} at {list(comp.location)}{mat_info}")
    print()

    # Verification
    print(f"Verification: {'OK' if verification.ok else 'ISSUES'}")
    if not verification.ok:
        print(verification.notes)
    print()

    # Script preview
    script_preview = result.get("script_preview", "")
    if script_preview:
        print("--- Script preview (first 40 lines) ---")
        for line in script_preview.splitlines()[:40]:
            print(line)
        print("--- End of preview ---")
    print()

    # Execution
    print(f"Execution: {'OK' if exec_result.ok else 'FAILED'}")
    if exec_result.stdout:
        print("\n--- Blender stdout ---")
        print(exec_result.stdout)
    if exec_result.stderr:
        print("\n--- Blender stderr ---")
        print(exec_result.stderr)
    print()

    # Inspection
    print(f"Inspection: {'OK' if inspection.ok else 'ISSUES'}")
    print(f"  Expected: {inspection.expected_count}, Found: {inspection.actual_count}")
    print(f"  {inspection.notes}")


if __name__ == "__main__":
    main()
