"""Load curated seed YAML into Neo4j (TODO).

Requirements (see docs/charter_data.md section 4):
- validate each service's stated TOTAL against the sum of step fees/times and report mismatches
- never auto-correct source data
- office-agnostic: adding an office must be data only
"""


def main() -> None:
    raise NotImplementedError("Implement in the loader session.")


if __name__ == "__main__":
    main()
