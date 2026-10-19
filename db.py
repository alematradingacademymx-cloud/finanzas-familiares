"""Lectura y escritura en el Google Sheet que sirve como base de datos."""
from __future__ import annotations

import json
import re

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Columnas de cada pestaña, en el mismo orden que en la hoja.
COLUMNAS = {
    "Usuarios": ["usuario", "nombre", "correo", "password_hash", "rol", "fecha_alta"],
    "Ingresos": ["id", "usuario", "fecha", "mes", "concepto", "monto", "tipo", "estado", "notas"],
    "Compromisos": ["id", "usuario", "concepto", "categoria", "monto", "dia_pago", "frecuencia",
                    "fecha_inicio", "activo", "recordatorio_dias", "notas"],
    "Pagos": ["id", "usuario", "compromiso_id", "mes", "concepto", "monto", "fecha_vencimiento",
              "estado", "fecha_pago", "monto_pagado", "evento_calendario_id", "notas"],
    "Gastos_Variables": ["id", "usuario", "fecha", "mes", "concepto", "categoria", "monto",
                         "metodo_pago", "notas"],
    "Metas": ["id", "usuario", "nombre", "costo", "fecha_objetivo", "actual", "faltante", "avance",
              "meses_restantes", "ahorro_mensual", "prioridad", "estado", "incluir_en_faltante"],
    "Aportaciones": ["id", "usuario", "meta_id", "fecha", "monto", "notas", "origen"],
    "Ahorro": ["id", "usuario", "fecha", "tipo", "monto", "notas"],
    "Creditos": ["id", "usuario", "nombre", "banco", "tipo", "limite", "dia_corte", "dia_pago", "activo", "notas",
                 "pago_total_intereses"],
    "Movimientos_Credito": ["id", "usuario", "credito_id", "fecha", "tipo", "monto", "notas"],
    "Categorias": ["tipo", "categoria"],
}

PREFIJOS = {
    "Ingresos": "ING", "Compromisos": "COM", "Pagos": "PAG",
    "Gastos_Variables": "GV", "Metas": "MET", "Aportaciones": "APO", "Ahorro": "AHO",
    "Creditos": "CRE", "Movimientos_Credito": "MCR",
}

# Columnas que se guardan como texto aunque parezcan números o fechas.
COLUMNAS_TEXTO = {"mes", "usuario", "password_hash", "id", "compromiso_id", "meta_id", "credito_id"}

# Columnas que la hoja calcula sola con ARRAYFORMULA: la app nunca las escribe.
COLUMNAS_FORMULA = {"Metas": {"actual", "faltante", "avance", "meses_restantes", "ahorro_mensual"}}


@st.cache_resource(show_spinner=False)
def _libro() -> gspread.Spreadsheet:
    # La llave puede venir pegada tal cual (gcp_json) o como sección TOML (gcp_service_account).
    if "gcp_json" in st.secrets:
        info = json.loads(st.secrets["gcp_json"])
    else:
        info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(st.secrets["sheet_id"])


def _hoja(tabla: str) -> gspread.Worksheet:
    return _libro().worksheet(tabla)


@st.cache_data(ttl=60, show_spinner=False)
def _todo() -> dict[str, list[list]]:
    """Lee todas las pestañas en una sola llamada a Google (cuida el límite de lecturas por minuto)."""
    tablas = list(COLUMNAS)
    resp = _libro().values_batch_get(
        [f"'{t}'!A:Z" for t in tablas],
        params={"valueRenderOption": "UNFORMATTED_VALUE", "dateTimeRenderOption": "FORMATTED_STRING"},
    )
    return {t: vr.get("values", []) for t, vr in zip(tablas, resp.get("valueRanges", []))}


def leer(tabla: str) -> pd.DataFrame:
    """Devuelve la pestaña como DataFrame. Incluye `_fila` (número de fila en la hoja)."""
    filas = _todo().get(tabla, [])
    cols = COLUMNAS[tabla]
    datos = []
    for i, fila in enumerate(filas[1:], start=2):
        fila = list(fila) + [""] * (len(cols) - len(fila))
        if not str(fila[0]).strip():
            continue
        datos.append(fila[: len(cols)] + [i])
    return pd.DataFrame(datos, columns=cols + ["_fila"])


def limpiar_cache() -> None:
    _todo.clear()


def _celda(columna: str, valor):
    """Prepara un valor para escribirlo sin que Sheets lo convierta en fórmula, número o fecha."""
    if valor is None:
        return ""
    if isinstance(valor, bool) or isinstance(valor, (int, float)):
        return valor
    texto = str(valor)
    if columna in COLUMNAS_TEXTO or texto[:1] in ("=", "+", "-", "@"):
        return "'" + texto
    return texto


def siguiente_id(tabla: str) -> str:
    prefijo = PREFIJOS[tabla]
    df = leer(tabla)
    numeros = [int(m.group(1)) for v in df["id"].astype(str)
               if (m := re.match(rf"{prefijo}-(\d+)$", v))]
    return f"{prefijo}-{(max(numeros) if numeros else 0) + 1:04d}"


def agregar(tabla: str, registros: list[dict]) -> list[str]:
    """Agrega filas al final de la pestaña. Asigna ids si la tabla los usa."""
    if not registros:
        return []
    cols = COLUMNAS[tabla]
    ids = []
    if tabla in PREFIJOS:
        prefijo = PREFIJOS[tabla]
        n = int(siguiente_id(tabla).split("-")[1])
        for r in registros:
            r["id"] = f"{prefijo}-{n:04d}"
            ids.append(r["id"])
            n += 1
    # Las columnas calculadas con fórmula en la hoja se mandan vacías (None) para no pisar la fórmula.
    calculadas = COLUMNAS_FORMULA.get(tabla, set())
    filas = [[None if c in calculadas else _celda(c, r.get(c, "")) for c in cols] for r in registros]
    _hoja(tabla).append_rows(filas, value_input_option="USER_ENTERED", table_range="A1")
    limpiar_cache()
    return ids


def actualizar(tabla: str, id_valor: str, cambios: dict, columna_id: str = "id") -> None:
    """Cambia algunas columnas de la fila cuyo id coincide."""
    limpiar_cache()
    df = leer(tabla)
    fila = df.loc[df[columna_id].astype(str) == str(id_valor), "_fila"]
    if fila.empty:
        raise ValueError(f"No encontré {id_valor} en {tabla}")
    n = int(fila.iloc[0])
    cols = COLUMNAS[tabla]
    datos = [
        {"range": gspread.utils.rowcol_to_a1(n, cols.index(c) + 1), "values": [[_celda(c, v)]]}
        for c, v in cambios.items()
    ]
    _hoja(tabla).batch_update(datos, value_input_option="USER_ENTERED")
    limpiar_cache()


def todas() -> dict[str, pd.DataFrame]:
    return {t: leer(t) for t in COLUMNAS}
