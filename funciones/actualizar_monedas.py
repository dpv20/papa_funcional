import requests
import pandas as pd
from funciones.monedas import load_monedas, save_monedas

def actualizar_indicadores() -> bool:
    """
    Obtiene los valores actuales de UF y Dólar desde mindicador.cl
    y actualiza el archivo monedas.csv.
    Retorna True si tuvo éxito, False si falló.
    """
    try:
        # 1. Obtener datos de la API
        # Timeout corto para no bloquear la UI mucho tiempo
        resp_uf = requests.get("https://mindicador.cl/api/uf", timeout=5)
        resp_dolar = requests.get("https://mindicador.cl/api/dolar", timeout=5)

        if resp_uf.status_code != 200 or resp_dolar.status_code != 200:
            return False

        data_uf = resp_uf.json()
        data_dolar = resp_dolar.json()

        # Extraer valores (la serie viene en 'serie', tomamos el primero que es el actual)
        # La API devuelve 'serie': [{'fecha': '...', 'valor': ...}, ...] ordenado desc
        valor_uf = data_uf["serie"][0]["valor"]
        valor_dolar = data_dolar["serie"][0]["valor"]

        # 2. Actualizar CSV usando funciones existentes
        df = load_monedas()
        
        # Actualizar UF
        mask_uf = df["Codigo"] == "UF"
        if mask_uf.any():
            df.loc[mask_uf, "ValorCLP"] = valor_uf
        else:
            # Si no existiera, se podría agregar, pero asumimos que existe por estructura base
            pass

        # Actualizar USD
        mask_usd = df["Codigo"] == "USD"
        if mask_usd.any():
            df.loc[mask_usd, "ValorCLP"] = valor_dolar
        else:
            pass

        save_monedas(df)
        return True

    except Exception as e:
        print(f"Error actualizando indicadores: {e}")
        return False
