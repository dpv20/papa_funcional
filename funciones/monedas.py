# funciones/monedas.py
import pandas as pd
from pathlib import Path
import streamlit as st

MONEDAS_PATH = Path("monedas.csv")


def load_monedas() -> pd.DataFrame:
    """Carga el archivo de monedas. Crea uno por defecto si no existe."""
    if MONEDAS_PATH.exists():
        df = pd.read_csv(MONEDAS_PATH)
    else:
        df = pd.DataFrame([
            {"Codigo": "CLP", "Nombre": "Peso Chileno", "ValorCLP": 1.0},
            {"Codigo": "UF", "Nombre": "Unidad de Fomento", "ValorCLP": 39718.89},
            {"Codigo": "USD", "Nombre": "Dólar Estadounidense", "ValorCLP": 862.07},
        ])
        save_monedas(df)
    
    # Asegurar tipos
    df["Codigo"] = df["Codigo"].astype(str)
    df["Nombre"] = df["Nombre"].astype(str)
    df["ValorCLP"] = pd.to_numeric(df["ValorCLP"], errors="coerce").fillna(1.0)
    return df


def save_monedas(df: pd.DataFrame) -> None:
    """Guarda el DataFrame de monedas al CSV."""
    tmp = MONEDAS_PATH.with_suffix(".tmp.csv")
    df.to_csv(tmp, index=False)
    tmp.replace(MONEDAS_PATH)


def get_moneda_value(codigo: str) -> float:
    """Obtiene el valor en CLP de una moneda por su código."""
    df = load_monedas()
    row = df[df["Codigo"].astype(str).str.upper() == str(codigo).upper()]
    if row.empty:
        return 1.0  # Default a CLP si no se encuentra
    return float(row["ValorCLP"].iloc[0])


def convert_clp_to(monto_clp: float, moneda_destino: str) -> float:
    """
    Convierte un monto en CLP a la moneda destino.
    Ejemplo: convert_clp_to(39718.89, "UF") → 1.0
    """
    valor = get_moneda_value(moneda_destino)
    if valor == 0:
        return 0.0
    return monto_clp / valor


def list_monedas_codes() -> list[str]:
    """Retorna lista de códigos de monedas disponibles."""
    df = load_monedas()
    return df["Codigo"].astype(str).tolist()
