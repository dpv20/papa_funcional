
import pandas as pd
from typing import List, Dict

def _parse_key(code: str):
    parts = []
    for seg in str(code).split("."):
        try:
            parts.append(int(seg))
        except:
            parts.append(0)
    return tuple(parts)

def _collect_parents(items: List[str]) -> List[str]:
    items = [str(x) for x in items if isinstance(x, str)]
    children_by_parent: Dict[str, List[str]] = {}
    for it in items:
        segs = it.split(".")
        if len(segs) >= 2:
            parent = segs[0]
            children_by_parent.setdefault(parent, []).append(it)
    parents = [p for p, childs in children_by_parent.items() if len(childs) > 0]
    return sorted(set(parents), key=_parse_key)

# Mock data simulating what might be in datos.csv
data = {
    "Item": ["1.00", "1.01", "2", "2.1"],
    "Partida": ["Descripcion 1.00", "Descripcion 1.01", "Descripcion 2", "Descripcion 2.1"]
}
df_datos = pd.DataFrame(data)

# Simulate logic in crear_detallado.py
items = sorted(df_datos["Item"].astype(str).tolist(), key=_parse_key)
print(f"Items: {items}")

parents = _collect_parents(items)
print(f"Parents: {parents}")

for p in parents:
    print(f"Checking parent: {p}")
    # Current logic
    row_p = df_datos[df_datos["Item"].astype(str) == str(p)]
    if not row_p.empty:
        desc = row_p.iloc[0]["Partida"]
        print(f"  FOUND exact match: {desc}")
    else:
        print(f"  NOT FOUND exact match for '{p}'")
        
    # Proposed logic: check for p.0, p.00
    candidates = [str(p), f"{p}.0", f"{p}.00"]
    mask = df_datos["Item"].astype(str).isin(candidates)
    row_p_flexible = df_datos[mask]
    if not row_p_flexible.empty:
         desc = row_p_flexible.iloc[0]["Partida"]
         print(f"  FOUND via flexible match: {desc}")
    else:
         print(f"  NOT FOUND via flexible match either")

