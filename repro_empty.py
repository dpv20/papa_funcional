
import pandas as pd
from typing import List, Dict, Tuple

def _parse_key(code: str) -> Tuple[int, ...]:
    parts = []
    for seg in str(code).split("."):
        try:
            parts.append(int(seg))
        except Exception:
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

def _children_of_parent(items: List[str], parent: str) -> List[str]:
    pref = parent + "."
    childs = [it for it in items if it.startswith(pref)]
    return sorted(childs, key=_parse_key)

# Mock data simulating what is in datos.csv
data = {
    "Item": ["1.01", "1.02", "2.01"],
    "Partida": ["hola", "partida 2", "test2"],
    "Fecha": ["26-01-26", "26-01-26", "26-01-26"],
    "cantidad tipo": ["Dia", "GL", "Gal"],
    "cantidad numero": [1, 1, 1],
    "moneda": ["UF", "CLP", "CLP"]
}

# The BUG: reading without dtype causes inference
df_datos = pd.DataFrame(data) # Pandas infers strings here because "Dia" etc are strings? No, Item 1.01 might be float.
# Let's verify standard read_csv behavior if file had numbers
import io
csv_content = """Item,Partida,Fecha,cantidad tipo,cantidad numero,moneda
1.01,hola,26-01-26,Dia,1,UF
1.02,partida 2,26-01-26,GL,1,CLP
2.01,test2,26-01-26,Gal,1,CLP
"""
df_datos = pd.read_csv(io.StringIO(csv_content)) 
# Without dtype, 1.01 is likely float 1.01

print("--- DataFrame loaded (simulating default read_csv) ---")
print(df_datos.dtypes)
print(df_datos["Item"].tolist())

items = sorted(df_datos["Item"].astype(str).tolist(), key=_parse_key)
parents = _collect_parents(items)
print(f"Parents: {parents}")

df_datos_idx = df_datos.set_index("Item")
print("--- Index ---")
print(df_datos_idx.index)

print("--- Checking children ---")
for parent in parents:
    childs = _children_of_parent(items, parent)
    print(f"Parent {parent} has children: {childs}")
    for child in childs:
        # The lookup logic in generar_excel_detallado
        # if child not in df_datos_idx.index:
        #    continue
        
        # Here lies the problem: child is string "1.01", index might be float 1.01
        if child in df_datos_idx.index:
             print(f"  [OK] Found child {child} in index")
        else:
             print(f"  [FAIL] Child {child} NOT in index (Index has {df_datos_idx.index.dtype})")
             try:
                 print(f"   value in index: {df_datos_idx.index[0]} type: {type(df_datos_idx.index[0])}")
             except: pass
