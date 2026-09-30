"""Read-only Cypher guardrail (TODO: implement in the guardrail session).

Contract (see docs/specs.md section 4):
- return a ValidationResult; never raise on bad input
- reject mutating/unsafe clauses, disallowed clauses, unknown schema elements,
  missing/excessive LIMIT, multiple statements, and obfuscation tricks
- use a tokenizer that handles string literals and comments correctly
Until implemented, this refuses everything (fail closed).
"""

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def validate_cypher(query: str) -> ValidationResult:
    return ValidationResult(ok=False, reasons=["guardrail not implemented (fail closed)"])
