"""Cálculos de la app. No depende de Streamlit ni de Google: solo recibe tablas (DataFrames)."""
from __future__ import annotations

import calendar
from datetime import date

import pandas as pd


# ---------- utilidades ----------

def mes_de(fecha: date) -> str:
    return f"{fecha.year:04d}-{fecha.month:02d}"


def sumar_meses(mes: str, n: int) -> str:
    y, m = map(int, mes.split("-"))
    total = y * 12 + (m - 1) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def a_fecha(valor) -> date | None:
    if valor in (None, "") or (isinstance(valor, float) and pd.isna(valor)):
        return None
    f = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(f) else f.date()


def a_num(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").fillna(0.0)


def es_verdadero(valor) -> bool:
    return str(valor).strip().upper() in ("TRUE", "VERDADERO", "1", "SI", "SÍ")


def del_usuario(df: pd.DataFrame, usuario: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df[df["usuario"].astype(str) == usuario].copy()


# ---------- generación de pagos a partir de los compromisos ----------

def fechas_en_mes(comp: dict, mes: str) -> list[date]:
    """Fechas en que vence un compromiso dentro de un mes, según su frecuencia."""
    y, m = map(int, mes.split("-"))
    ultimo = calendar.monthrange(y, m)[1]
    try:
        dia = max(1, min(31, int(float(comp.get("dia_pago") or 1))))
    except ValueError:
        dia = 1
    inicio = a_fecha(comp.get("fecha_inicio")) or date(y, m, 1)
    meses_desde = (y - inicio.year) * 12 + (m - inicio.month)
    if meses_desde < 0:
        return []

    frecuencia = str(comp.get("frecuencia") or "Mensual")
    if frecuencia == "Quincenal":
        dias = [dia, dia + 15] if dia <= 15 else [dia - 15, dia]
    elif frecuencia == "Bimestral":
        dias = [dia] if meses_desde % 2 == 0 else []
    elif frecuencia == "Anual":
        dias = [dia] if meses_desde % 12 == 0 else []
    elif frecuencia == "Única":
        dias = [dia] if meses_desde == 0 else []
    else:  # Mensual
        dias = [dia]

    fechas = [date(y, m, min(d, ultimo)) for d in dias]
    return [f for f in fechas if f >= inicio]


def pagos_por_generar(compromisos: pd.DataFrame, pagos: pd.DataFrame, usuario: str, mes: str) -> list[dict]:
    """Pagos del mes que faltan en la pestaña Pagos (sin id; el id lo pone db)."""
    comps = del_usuario(compromisos, usuario)
    if comps.empty:
        return []
    comps = comps[comps["activo"].apply(es_verdadero)]

    existentes = set()
    for _, p in del_usuario(pagos, usuario).iterrows():
        f = a_fecha(p.get("fecha_vencimiento"))
        existentes.add((str(p.get("compromiso_id")), f))

    nuevos = []
    for _, c in comps.iterrows():
        for f in fechas_en_mes(c.to_dict(), mes):
            if (str(c["id"]), f) in existentes:
                continue
            nuevos.append({
                "usuario": usuario,
                "compromiso_id": c["id"],
                "mes": mes,
                "concepto": c["concepto"],
                "monto": float(pd.to_numeric(c["monto"], errors="coerce") or 0),
                "fecha_vencimiento": f.isoformat(),
                "estado": "Pendiente",
            })
    return nuevos


# ---------- metas de ahorro ----------

def meses_restantes(objetivo: date | None, hoy: date) -> int:
    """Meses que quedan para ahorrar, contando el mes actual como 0 y mínimo 1."""
    if objetivo is None:
        return 1
    return max(1, (objetivo.year - hoy.year) * 12 + objetivo.month - hoy.month)


def metas_usuario(t: dict[str, pd.DataFrame], usuario: str, hoy: date | None = None) -> pd.DataFrame:
    """Metas del usuario con lo ahorrado, lo que falta y cuánto apartar al mes."""
    hoy = hoy or date.today()
    cols = ["id", "nombre", "costo", "fecha_objetivo", "actual", "faltante", "avance",
            "meses", "ahorro_mensual", "prioridad", "estado", "incluir"]
    met = del_usuario(t["Metas"], usuario)
    if met.empty:
        return pd.DataFrame(columns=cols)
    apo = del_usuario(t["Aportaciones"], usuario)
    por_meta = (a_num(apo["monto"]).groupby(apo["meta_id"].astype(str)).sum()
                if not apo.empty else pd.Series(dtype=float))

    filas = []
    for _, m in met.iterrows():
        costo = float(pd.to_numeric(m["costo"], errors="coerce") or 0)
        actual = float(por_meta.get(str(m["id"]), 0.0))
        faltante = max(0.0, costo - actual)
        objetivo = a_fecha(m["fecha_objetivo"])
        meses = meses_restantes(objetivo, hoy)
        estado = str(m["estado"] or "Activa")
        filas.append({
            "id": m["id"], "nombre": m["nombre"], "costo": costo, "fecha_objetivo": objetivo,
            "actual": actual, "faltante": faltante,
            "avance": 0.0 if costo == 0 else min(1.0, actual / costo),
            "meses": meses,
            "ahorro_mensual": 0.0 if estado != "Activa" else faltante / meses,
            "prioridad": m["prioridad"] or "Media", "estado": estado,
            "incluir": es_verdadero(m["incluir_en_faltante"]),
        })
    return pd.DataFrame(filas, columns=cols)


# ---------- resumen del mes ----------

def resumen_mes(t: dict[str, pd.DataFrame], usuario: str, mes: str) -> dict:
    ing = del_usuario(t["Ingresos"], usuario)
    pag = del_usuario(t["Pagos"], usuario)
    gv = del_usuario(t["Gastos_Variables"], usuario)

    def suma(df, col, **filtros):
        if df.empty:
            return 0.0
        m = df["mes"].astype(str) == mes if "mes" in df else pd.Series(True, index=df.index)
        for k, v in filtros.items():
            m &= df[k].astype(str) == v
        return float(a_num(df.loc[m, col]).sum())

    recibidos = suma(ing, "monto", estado="Recibido")
    esperados = suma(ing, "monto", estado="Esperado")
    pagado = suma(pag, "monto_pagado", estado="Pagado")
    variables = suma(gv, "monto")
    pendientes = suma(pag, "monto", estado="Pendiente")

    ahorro_metas = 0.0
    met = metas_usuario(t, usuario)
    if not met.empty:
        activas = met[(met["estado"] == "Activa") & met["incluir"]]
        ahorro_metas = float(activas["ahorro_mensual"].sum())

    disponible = recibidos - pagado - variables
    return {
        "ingresos_recibidos": recibidos,
        "ingresos_esperados": esperados,
        "pagos_realizados": pagado,
        "gastos_variables": variables,
        "disponible": disponible,
        "pagos_pendientes": pendientes,
        "ahorro_metas": ahorro_metas,
        "faltante": max(0.0, pendientes + ahorro_metas - disponible),
        "faltante_con_esperados": max(0.0, pendientes + ahorro_metas - disponible - esperados),
    }


# ---------- saldo y calendario de pagos ----------

def movimientos_ahorro(t: dict[str, pd.DataFrame], usuario: str) -> pd.DataFrame:
    """Depósitos (+) y retiros (-) del ahorro libre, en orden de fecha."""
    aho = del_usuario(t.get("Ahorro", pd.DataFrame()), usuario)
    if aho.empty:
        return pd.DataFrame(columns=["id", "fecha", "tipo", "monto", "con_signo", "notas"])
    aho = aho.assign(fecha=aho["fecha"].apply(a_fecha), monto=a_num(aho["monto"]))
    aho["con_signo"] = aho["monto"].where(aho["tipo"] != "Retiro", -aho["monto"])
    return aho.sort_values("fecha", na_position="last")[["id", "fecha", "tipo", "monto", "con_signo", "notas"]]


def saldo_ahorro(t: dict[str, pd.DataFrame], usuario: str) -> float:
    return float(movimientos_ahorro(t, usuario)["con_signo"].sum())


def saldo_actual(t: dict[str, pd.DataFrame], usuario: str) -> float:
    """Dinero que tienes hoy: lo recibido menos lo pagado, gastado, apartado en metas y guardado en ahorro."""
    ing = del_usuario(t["Ingresos"], usuario)
    pag = del_usuario(t["Pagos"], usuario)
    gv = del_usuario(t["Gastos_Variables"], usuario)
    apo = del_usuario(t["Aportaciones"], usuario)
    recibido = a_num(ing.loc[ing["estado"] == "Recibido", "monto"]).sum() if not ing.empty else 0
    pagado = a_num(pag.loc[pag["estado"] == "Pagado", "monto_pagado"]).sum() if not pag.empty else 0
    gastado = a_num(gv["monto"]).sum() if not gv.empty else 0
    apartado = a_num(apo["monto"]).sum() if not apo.empty else 0
    return float(recibido - pagado - gastado - apartado - saldo_ahorro(t, usuario))


# ---------- historial ----------

def ultimos_meses(actual: str, n: int) -> list[str]:
    return [sumar_meses(actual, -i) for i in range(n - 1, -1, -1)]


def _mes_de_valor(v) -> str | None:
    f = a_fecha(v)
    return mes_de(f) if f else None


def historial_mensual(t: dict[str, pd.DataFrame], usuario: str, meses: list[str]) -> pd.DataFrame:
    """Por mes: ingresos, pagos fijos, gastos variables, balance y lo que pasó a ahorro y metas."""
    ing = del_usuario(t["Ingresos"], usuario)
    pag = del_usuario(t["Pagos"], usuario)
    gv = del_usuario(t["Gastos_Variables"], usuario)
    apo = del_usuario(t["Aportaciones"], usuario)
    mov = movimientos_ahorro(t, usuario)

    def por_mes(df, col_fecha, valores) -> pd.Series:
        if df.empty:
            return pd.Series(0.0, index=meses)
        m = df[col_fecha].apply(_mes_de_valor)
        return pd.Series(list(valores), index=m.values).groupby(level=0).sum().reindex(meses, fill_value=0.0)

    if not ing.empty:  # el saldo inicial no es un ingreso del mes
        ing = ing[(ing["estado"] == "Recibido") & (ing["tipo"] != "Saldo inicial")]
    if not pag.empty:
        pag = pag[pag["estado"] == "Pagado"]

    ingresos = por_mes(ing, "fecha", a_num(ing["monto"]) if not ing.empty else [])
    pagos = por_mes(pag, "fecha_pago", a_num(pag["monto_pagado"]) if not pag.empty else [])
    variables = por_mes(gv, "fecha", a_num(gv["monto"]) if not gv.empty else [])
    a_metas = por_mes(apo, "fecha", a_num(apo["monto"]) if not apo.empty else [])
    a_ahorro = por_mes(mov, "fecha", mov["con_signo"] if not mov.empty else [])

    df = pd.DataFrame({
        "ingresos": ingresos, "pagos_fijos": pagos, "gastos_variables": variables,
        "a_ahorro": a_ahorro, "a_metas": a_metas,
    }, index=meses).fillna(0.0)
    df["gastos"] = df["pagos_fijos"] + df["gastos_variables"]
    df["balance"] = df["ingresos"] - df["gastos"]
    return df


def gastos_por_categoria(t: dict[str, pd.DataFrame], usuario: str, meses: list[str]) -> pd.Series:
    """Total gastado por categoría (pagos fijos pagados + gastos variables) en los meses indicados."""
    partes = []
    pag = del_usuario(t["Pagos"], usuario)
    if not pag.empty:
        pag = pag[(pag["estado"] == "Pagado") & pag["fecha_pago"].apply(_mes_de_valor).isin(meses)]
        comps = del_usuario(t["Compromisos"], usuario)
        cat = dict(zip(comps["id"].astype(str), comps["categoria"])) if not comps.empty else {}
        partes.append(pd.Series(a_num(pag["monto_pagado"]).values,
                                index=pag["compromiso_id"].astype(str).map(cat).fillna("Otros").values))
    gv = del_usuario(t["Gastos_Variables"], usuario)
    if not gv.empty:
        gv = gv[gv["fecha"].apply(_mes_de_valor).isin(meses)]
        partes.append(pd.Series(a_num(gv["monto"]).values, index=gv["categoria"].replace("", "Otros").values))
    if not partes:
        return pd.Series(dtype=float)
    total = pd.concat(partes).groupby(level=0).sum()
    return total[total > 0].sort_values(ascending=False)


def ahorro_acumulado(t: dict[str, pd.DataFrame], usuario: str, meses: list[str]) -> pd.DataFrame:
    """Saldo al cierre de cada mes del ahorro libre y de lo aportado a metas."""
    mov = movimientos_ahorro(t, usuario)
    apo = del_usuario(t["Aportaciones"], usuario)
    filas = []
    for m in meses:
        y, mm = map(int, m.split("-"))
        fin = date(y, mm, calendar.monthrange(y, mm)[1])
        libre = mov.loc[mov["fecha"].apply(lambda f: f is not None and f <= fin), "con_signo"].sum() if not mov.empty else 0
        metas = (a_num(apo.loc[apo["fecha"].apply(lambda f: (a_fecha(f) or date.max) <= fin), "monto"]).sum()
                 if not apo.empty else 0)
        filas.append({"mes": m, "Ahorro": float(libre), "Metas": float(metas)})
    return pd.DataFrame(filas).set_index("mes")


def calendario_pagos(t: dict[str, pd.DataFrame], usuario: str, hoy: date) -> pd.DataFrame:
    """Pagos pendientes en orden de fecha, con lo acumulado y si tu dinero alcanza para cada uno."""
    pag = del_usuario(t["Pagos"], usuario)
    cols = ["id", "concepto", "fecha", "monto", "acumulado", "estado", "falta"]
    if pag.empty:
        return pd.DataFrame(columns=cols)
    pend = pag[pag["estado"] == "Pendiente"].copy()
    if pend.empty:
        return pd.DataFrame(columns=cols)

    pend["fecha"] = pend["fecha_vencimiento"].apply(a_fecha)
    pend["monto"] = a_num(pend["monto"])
    pend = pend.sort_values("fecha", na_position="last")
    pend["acumulado"] = pend["monto"].cumsum()

    ing = del_usuario(t["Ingresos"], usuario)
    esperados = ing[ing["estado"] == "Esperado"].copy() if not ing.empty else ing
    if not esperados.empty:
        esperados["fecha_d"] = esperados["fecha"].apply(a_fecha)
        esperados["monto_n"] = a_num(esperados["monto"])

    saldo = saldo_actual(t, usuario)
    estados, faltas = [], []
    for _, p in pend.iterrows():
        llega = 0.0
        if not esperados.empty and p["fecha"]:
            llega = float(esperados.loc[esperados["fecha_d"].apply(lambda d: d is not None and d <= p["fecha"]), "monto_n"].sum())
        if saldo >= p["acumulado"]:
            est, falta = "Cubierto", 0.0
        elif saldo + llega >= p["acumulado"]:
            est, falta = "Cubierto con ingreso esperado", 0.0
        else:
            falta = p["acumulado"] - saldo - llega
            est = "No alcanza"
        if p["fecha"] and p["fecha"] < hoy:
            est = "Vencido · " + est
        estados.append(est)
        faltas.append(falta)
    pend["estado"] = estados
    pend["falta"] = faltas
    return pend[cols].reset_index(drop=True)
