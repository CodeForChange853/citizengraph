"""Word lists of the guardrail (docs/specs.md section 4). Compared in upper case."""

# Mutating or unsafe (docs/specs.md section 4). CALL is denied outright, including apoc.*.
FORBIDDEN_KEYWORDS = frozenset(
    {"CREATE", "MERGE", "SET", "DELETE", "DETACH", "REMOVE", "DROP", "FOREACH", "LOAD", "CALL"}
)
# Not mutating in themselves, but outside the clause allow-list. Words that are also legal
# variable names in Cypher are rejected as variables too: over-rejecting is the safe side.
DISALLOWED_CLAUSES = frozenset(
    {
        "CSV",
        "YIELD",
        "UNION",
        "USE",
        "USING",
        "START",
        "FINISH",
        "SHOW",
        "TERMINATE",
        "ALTER",
        "GRANT",
        "DENY",
        "REVOKE",
        "RENAME",
        "CONSTRAINT",
        "INDEX",
        "PROFILE",
        "EXPLAIN",
        "CYPHER",
        "INSERT",
        "FILTER",
        "LET",
        "NEXT",
        "OFFSET",
        "ON",
        "COMMIT",
        "TRANSACTIONS",
    }
)
# Clause words allowed to open a query, and clauses that may not follow the final RETURN.
OPENERS = frozenset({"MATCH", "OPTIONAL", "WITH", "UNWIND", "RETURN"})
CLAUSE_STARTERS = frozenset({"MATCH", "OPTIONAL", "WHERE", "WITH", "UNWIND", "RETURN"})
# Functions that expose properties the schema check cannot see.
FORBIDDEN_FUNCTIONS = frozenset({"PROPERTIES", "KEYS"})
# A `[` after any other word, `)`, `]`, string, number or parameter is a subscript such as
# `s['secret']`, which would read a property by a dynamic key. BY counts only after ORDER.
LIST_PREFIX_KEYWORDS = frozenset(
    {
        "IN",
        "RETURN",
        "WHERE",
        "AND",
        "OR",
        "XOR",
        "NOT",
        "WITH",
        "UNWIND",
        "BY",
        "THEN",
        "ELSE",
        "WHEN",
        "CASE",
        "CONTAINS",
    }
)
# `{` after one of these opens a subquery, not a map.
SUBQUERY_WORDS = frozenset({"EXISTS", "COUNT", "COLLECT"})
# Every other word the guardrail reads as syntax and not as a name.
SYNTAX_WORDS = frozenset(
    {
        "ORDER",
        "BY",
        "SKIP",
        "LIMIT",
        "ASC",
        "DESC",
        "ASCENDING",
        "DESCENDING",
        "DISTINCT",
        "AS",
        "AND",
        "OR",
        "XOR",
        "NOT",
        "IN",
        "IS",
        "NULL",
        "TRUE",
        "FALSE",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "END",
        "STARTS",
        "ENDS",
        "CONTAINS",
        "REDUCE",
    }
)
# A variable with one of these names would be read by the guardrail as syntax while the
# database reads it as a variable (`by['x']` after ORDER-less BY, `MATCH unwind = (...)`),
# so no variable or alias may carry one.
KEYWORDS = (
    FORBIDDEN_KEYWORDS
    | DISALLOWED_CLAUSES
    | OPENERS
    | CLAUSE_STARTERS
    | FORBIDDEN_FUNCTIONS
    | LIST_PREFIX_KEYWORDS
    | SUBQUERY_WORDS
    | SYNTAX_WORDS
)
