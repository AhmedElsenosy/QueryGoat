"""LLM prompt templates for the daily puzzle agent.

Keep all prompt text here so it is easy to tune without touching node logic.
"""

REWRITE_SYSTEM = """\
You are rewriting SQL puzzle questions to be clear, self-contained problem \
statements like LeetCode SQL problems.

Rules:
1. Write one sentence for the task, one for the return type.
2. Expand cryptic column abbreviations (e.g. "Edispl" -> "engine displacement \
(Edispl)").
3. Mention exact column and table names when they are non-obvious.
4. Mention filter values in the exact case stored in the database (e.g. \
"volvo" if lowercase).
5. Do NOT use table aliases like T1 or T2.
6. Do NOT reveal the computed answer.
7. Do NOT mention tables the gold query does not use.
8. Keep it concise and clear."""

REWRITE_USER = """\
Original question: {original_prompt}

Database schema and sample data:
{schema_text}

Rewrite this as a clear SQL puzzle problem statement.
Return ONLY the rewritten text, nothing else."""

VERIFY_SYSTEM = """\
You are a SQL expert. Write a SQLite query to solve the given problem.
Return ONLY the SQL query. No explanations, no markdown fences, no comments."""

VERIFY_USER = """\
Problem: {rewritten_prompt}

Database: SQLite

Schema and sample data:
{schema_text}

Expected output shape: {col_count} column(s), {row_count} row(s).

Write the SQL query to solve this problem."""
