from __future__ import annotations

import re


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().lower())


def is_select_star(sql: str) -> bool:
    collapsed = re.sub(r"\s+", " ", sql.strip().lower())
    return bool(re.match(r"select\s+(distinct\s+)?\*\s+from\b", collapsed))


def classify_difficulty(sql: str) -> str:
    q = f" {sql.lower()} "
    n_select = q.count(" select ")
    n_join = q.count(" join ")
    n_where = q.count(" where ")
    n_group = q.count(" group by ")
    n_order = q.count(" order by ")
    n_having = q.count(" having ")
    n_iuen = sum(q.count(f" {op} ") for op in ("intersect", "union", "except"))
    comps = 0
    if n_where:
        comps += 1
    if n_group:
        comps += 1
    if n_order:
        comps += 1
    if n_having:
        comps += 1
    if n_join:
        comps += 1
    if n_select > 1:
        comps += 2
    if n_iuen:
        comps += 2
    if n_join >= 2:
        comps += 1
    if n_select >= 3:
        comps += 1
    if comps <= 1 and n_select <= 1 and n_join == 0 and n_iuen == 0:
        return "easy"
    if comps <= 2 and n_iuen == 0 and n_select <= 2:
        return "medium"
    if comps <= 4:
        return "hard"
    return "extra"
