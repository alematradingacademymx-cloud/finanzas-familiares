"""Finanzas Familiares: ingresos, gastos fijos, pagos y cuánto falta por juntar."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import auth
import db
import logic

st.set_page_config(page_title="Finanzas Familiares", page_icon=":material/savings:", layout="centered")

FRECUENCIAS = ["Mensual", "Quincenal", "Bimestral", "Anual", "Única"]
METODOS = ["Efectivo", "Débito", "Crédito", "Transferencia"]
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
            "septiembre", "octubre", "noviembre", "diciembre"]


def hoy() -> date:
    return datetime.now(ZoneInfo("America/Mexico_City")).date()


def dinero(x: float) -> str:
    return f"${x:,.2f}"


def fecha_txt(d) -> str:
    return d.strftime("%d/%m/%Y") if isinstance(d, date) else "sin fecha"


def nombre_mes(mes: str) -> str:
    y, m = map(int, mes.split("-"))
    return f"{MESES_ES[m - 1].capitalize()} {y}"


def generar_pagos(usuario: str) -> int:
    """Crea en la pestaña Pagos los pagos de este mes y del siguiente que aún no existan."""
    db.limpiar_cache()
    t = db.todas()
    actual = logic.mes_de(hoy())
    nuevos = []
    for m in (actual, logic.sumar_meses(actual, 1)):
        nuevos += logic.pagos_por_generar(t["Compromisos"], t["Pagos"], usuario, m)
    db.agregar("Pagos", nuevos)
    return len(nuevos)


# ---------- acceso ----------

if "usuario" not in st.session_state:
    auth.pantalla_acceso()
    st.stop()

U = st.session_state.usuario

if not st.session_state.get("pagos_generados"):
    generar_pagos(U)
    st.session_state.pagos_generados = True

# ---------- menú lateral ----------

with st.sidebar:
    st.subheader(f"Hola, {st.session_state.nombre}")
    pagina = st.radio("Menú", ["Resumen", "Ingresos", "Pagos y gastos fijos", "Gastos variables"])
    actual = logic.mes_de(hoy())
    meses = [logic.sumar_meses(actual, i) for i in range(-6, 3)]
    mes = st.selectbox("Mes", meses, index=6, format_func=nombre_mes)
    st.divider()
    if st.button("Actualizar datos"):
        db.limpiar_cache()
        st.rerun()
    if st.button("Cerrar sesión"):
        auth.cerrar_sesion()

t = db.todas()
cats = t["Categorias"]
CAT_GASTO = cats.loc[cats["tipo"] == "Gasto", "categoria"].tolist() or ["Otros"]
CAT_INGRESO = cats.loc[cats["tipo"] == "Ingreso", "categoria"].tolist() or ["Otros"]


def tabla_usuario(nombre: str) -> pd.DataFrame:
    return logic.del_usuario(t[nombre], U)


# ---------- páginas ----------

def pagina_resumen() -> None:
    st.title(f"Resumen de {nombre_mes(mes)}")
    r = logic.resumen_mes(t, U, mes)

    c1, c2 = st.columns(2)
    c1.metric("Ingresos recibidos", dinero(r["ingresos_recibidos"]))
    c2.metric("Ingresos por cobrar", dinero(r["ingresos_esperados"]))
    c3, c4 = st.columns(2)
    c3.metric("Gastado (pagos + variables)", dinero(r["pagos_realizados"] + r["gastos_variables"]))
    c4.metric("Disponible del mes", dinero(r["disponible"]))

    if r["faltante"] == 0:
        st.success("Con lo que ya recibiste alcanzas a cubrir los pagos y el ahorro de este mes.")
    elif r["faltante_con_esperados"] == 0:
        st.warning(f"Hoy te faltan {dinero(r['faltante'])}, pero con los ingresos que esperas este mes sí alcanzas.")
    else:
        st.error(f"Te faltan {dinero(r['faltante_con_esperados'])} para cubrir este mes, "
                 "aun contando los ingresos que esperas.")

    with st.expander("Ver el cálculo"):
        st.write(pd.DataFrame({
            "Concepto": ["Ingresos recibidos", "Pagos realizados", "Gastos variables", "Disponible",
                         "Pagos pendientes", "Ahorro mensual para metas", "Faltante por juntar",
                         "Ingresos por cobrar", "Faltante contando ingresos por cobrar"],
            "Monto": [dinero(r[k]) for k in ("ingresos_recibidos", "pagos_realizados", "gastos_variables",
                                             "disponible", "pagos_pendientes", "ahorro_metas", "faltante",
                                             "ingresos_esperados", "faltante_con_esperados")],
        }).set_index("Concepto"))

    st.subheader("Calendario de pagos")
    cal = logic.calendario_pagos(t, U, hoy())
    saldo = logic.saldo_actual(t, U)
    st.caption(f"Dinero disponible hoy (todo lo recibido menos lo pagado, gastado y apartado en metas): {dinero(saldo)}")
    if cal.empty:
        st.info("No tienes pagos pendientes.")
        return
    p = cal.iloc[0]
    texto = f"Próximo pago: **{p['concepto']}** el {fecha_txt(p['fecha'])} por **{dinero(p['monto'])}**."
    if p["falta"] > 0:
        texto += f" Te faltan **{dinero(p['falta'])}** para cubrirlo."
    st.info(texto)

    vista = pd.DataFrame({
        "Fecha": cal["fecha"].apply(fecha_txt),
        "Pago": cal["concepto"],
        "Monto": cal["monto"].apply(dinero),
        "Acumulado": cal["acumulado"].apply(dinero),
        "Estado": cal["estado"],
        "Falta": cal["falta"].apply(lambda x: dinero(x) if x > 0 else ""),
    })

    def color(fila):
        e = fila["Estado"]
        fondo = "#FCE4E4" if "No alcanza" in e else "#FFF2CC" if "esperado" in e else "#D9EAD3"
        return [f"background-color: {fondo}; color: #1a1a1a"] * len(fila)

    st.dataframe(vista.style.apply(color, axis=1), hide_index=True)


def pagina_ingresos() -> None:
    st.title("Ingresos")
    with st.form("nuevo_ingreso", clear_on_submit=True):
        st.subheader("Registrar ingreso")
        c1, c2 = st.columns(2)
        fecha = c1.date_input("Fecha", value=hoy(), format="DD/MM/YYYY")
        monto = c2.number_input("Monto", min_value=0.0, step=100.0, format="%.2f")
        concepto = st.selectbox("Concepto", CAT_INGRESO, accept_new_options=True)
        c3, c4 = st.columns(2)
        tipo = c3.radio("Tipo", ["Fijo", "Variable"], horizontal=True)
        estado = c4.radio("Estado", ["Recibido", "Esperado"], horizontal=True,
                          help="Esperado: aún no te pagan, pero sabes que llegará en esa fecha.")
        notas = st.text_input("Notas (opcional)")
        if st.form_submit_button("Guardar ingreso", type="primary"):
            if monto <= 0:
                st.error("Escribe un monto mayor a cero.")
            else:
                db.agregar("Ingresos", [{
                    "usuario": U, "fecha": fecha.isoformat(), "mes": logic.mes_de(fecha),
                    "concepto": concepto, "monto": monto, "tipo": tipo, "estado": estado, "notas": notas,
                }])
                st.toast("Ingreso guardado")
                st.rerun()

    st.subheader(f"Ingresos de {nombre_mes(mes)}")
    ing = tabla_usuario("Ingresos")
    ing = ing[ing["mes"].astype(str) == mes] if not ing.empty else ing
    if ing.empty:
        st.info("Aún no hay ingresos en este mes.")
        return
    for _, i in ing.sort_values("fecha").iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            c1.markdown(f"**{i['concepto']}**  \n{i['fecha']} · {i['tipo']}")
            c2.markdown(f"**{dinero(float(i['monto'] or 0))}**  \n{i['estado']}")
            if i["estado"] == "Esperado" and c3.button("Marcar recibido", key=f"rec_{i['id']}"):
                db.actualizar("Ingresos", i["id"], {"estado": "Recibido", "fecha": hoy().isoformat()})
                st.rerun()
    total = logic.a_num(ing.loc[ing["estado"] == "Recibido", "monto"]).sum()
    st.caption(f"Total recibido en el mes: {dinero(total)}")


def pagina_pagos() -> None:
    st.title("Pagos y gastos fijos")
    por_pagar, fijos, historial = st.tabs(["Por pagar", "Mis gastos fijos", "Historial"])

    with por_pagar:
        cal = logic.calendario_pagos(t, U, hoy())
        if cal.empty:
            st.info("No tienes pagos pendientes. Agrega tus gastos fijos en la pestaña Mis gastos fijos.")
        for _, p in cal.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 2])
                c1.markdown(f"**{p['concepto']}**  \nVence el {fecha_txt(p['fecha'])}")
                c2.markdown(f"**{dinero(p['monto'])}**  \n{p['estado']}")
                with st.expander("Registrar pago"):
                    with st.form(f"pagar_{p['id']}"):
                        a, b = st.columns(2)
                        monto = a.number_input("Monto pagado", min_value=0.0, value=float(p["monto"]),
                                               step=50.0, format="%.2f")
                        fecha = b.date_input("Fecha de pago", value=hoy(), format="DD/MM/YYYY")
                        if st.form_submit_button("Confirmar pago", type="primary"):
                            db.actualizar("Pagos", p["id"], {
                                "estado": "Pagado", "fecha_pago": fecha.isoformat(), "monto_pagado": monto,
                            })
                            st.toast(f"{p['concepto']} marcado como pagado")
                            st.rerun()

    with fijos:
        with st.form("nuevo_compromiso", clear_on_submit=True):
            st.subheader("Agregar gasto fijo")
            concepto = st.text_input("Concepto (ej. Renta, Internet, Tarjeta)")
            c1, c2 = st.columns(2)
            categoria = c1.selectbox("Categoría", CAT_GASTO)
            monto = c2.number_input("Monto", min_value=0.0, step=100.0, format="%.2f")
            c3, c4 = st.columns(2)
            dia = c3.number_input("Día de pago", min_value=1, max_value=31, value=1)
            frecuencia = c4.selectbox("Frecuencia", FRECUENCIAS,
                                      help="Quincenal: se paga el día indicado y 15 días después.")
            c5, c6 = st.columns(2)
            inicio = c5.date_input("Empieza en", value=hoy().replace(day=1), format="DD/MM/YYYY")
            aviso = c6.number_input("Avisarme días antes", min_value=0, max_value=15, value=3)
            if st.form_submit_button("Guardar gasto fijo", type="primary"):
                if not concepto.strip() or monto <= 0:
                    st.error("Escribe el concepto y un monto mayor a cero.")
                else:
                    db.agregar("Compromisos", [{
                        "usuario": U, "concepto": concepto.strip(), "categoria": categoria, "monto": monto,
                        "dia_pago": int(dia), "frecuencia": frecuencia, "fecha_inicio": inicio.isoformat(),
                        "activo": True, "recordatorio_dias": int(aviso),
                    }])
                    n = generar_pagos(U)
                    st.toast(f"Gasto fijo guardado. Se agregaron {n} pagos al calendario.")
                    st.rerun()

        comps = tabla_usuario("Compromisos")
        if comps.empty:
            st.info("Aún no tienes gastos fijos.")
        else:
            st.subheader("Tus gastos fijos")
            for _, c in comps.iterrows():
                activo = logic.es_verdadero(c["activo"])
                with st.container(border=True):
                    a, b, d = st.columns([3, 2, 2])
                    a.markdown(f"**{c['concepto']}**  \n{c['categoria']} · {c['frecuencia']}, día {c['dia_pago']}")
                    b.markdown(f"**{dinero(float(c['monto'] or 0))}**  \n{'Activo' if activo else 'Inactivo'}")
                    etiqueta = "Desactivar" if activo else "Activar"
                    if d.button(etiqueta, key=f"act_{c['id']}"):
                        db.actualizar("Compromisos", c["id"], {"activo": not activo})
                        if not activo:
                            generar_pagos(U)
                        st.rerun()
            mensual = comps[comps["activo"].apply(logic.es_verdadero) & (comps["frecuencia"] == "Mensual")]
            st.caption(f"Total de gastos fijos mensuales activos: {dinero(logic.a_num(mensual['monto']).sum())}")

    with historial:
        pag = tabla_usuario("Pagos")
        pagados = pag[pag["estado"] == "Pagado"] if not pag.empty else pag
        todos = st.toggle("Ver todos los meses")
        if not todos and not pagados.empty:
            pagados = pagados[pagados["mes"].astype(str) == mes]
        if pagados.empty:
            st.info("No hay pagos registrados en este periodo.")
        else:
            pagados = pagados.sort_values("fecha_pago", ascending=False)
            st.dataframe(pd.DataFrame({
                "Pago": pagados["concepto"],
                "Vencía": pagados["fecha_vencimiento"],
                "Pagado el": pagados["fecha_pago"],
                "Monto pagado": logic.a_num(pagados["monto_pagado"]).apply(dinero),
            }), hide_index=True)
            st.caption(f"Total pagado: {dinero(logic.a_num(pagados['monto_pagado']).sum())}")


def pagina_gastos() -> None:
    st.title("Gastos variables")
    with st.form("nuevo_gasto", clear_on_submit=True):
        st.subheader("Registrar gasto")
        c1, c2 = st.columns(2)
        fecha = c1.date_input("Fecha", value=hoy(), format="DD/MM/YYYY")
        monto = c2.number_input("Monto", min_value=0.0, step=50.0, format="%.2f")
        concepto = st.text_input("Concepto (ej. Despensa, Gasolina)")
        c3, c4 = st.columns(2)
        categoria = c3.selectbox("Categoría", CAT_GASTO)
        metodo = c4.selectbox("Método de pago", METODOS)
        if st.form_submit_button("Guardar gasto", type="primary"):
            if not concepto.strip() or monto <= 0:
                st.error("Escribe el concepto y un monto mayor a cero.")
            else:
                db.agregar("Gastos_Variables", [{
                    "usuario": U, "fecha": fecha.isoformat(), "mes": logic.mes_de(fecha),
                    "concepto": concepto.strip(), "categoria": categoria, "monto": monto, "metodo_pago": metodo,
                }])
                st.toast("Gasto guardado")
                st.rerun()

    gv = tabla_usuario("Gastos_Variables")
    gv = gv[gv["mes"].astype(str) == mes] if not gv.empty else gv
    st.subheader(f"Gastos de {nombre_mes(mes)}")
    if gv.empty:
        st.info("Aún no hay gastos variables en este mes.")
        return
    gv = gv.assign(monto_n=logic.a_num(gv["monto"]))
    st.dataframe(pd.DataFrame({
        "Fecha": gv["fecha"], "Concepto": gv["concepto"], "Categoría": gv["categoria"],
        "Monto": gv["monto_n"].apply(dinero), "Método": gv["metodo_pago"],
    }).sort_values("Fecha", ascending=False), hide_index=True)
    st.caption(f"Total del mes: {dinero(gv['monto_n'].sum())}")
    st.bar_chart(gv.groupby("categoria")["monto_n"].sum(), horizontal=True, x_label="Monto", y_label="")


{
    "Resumen": pagina_resumen,
    "Ingresos": pagina_ingresos,
    "Pagos y gastos fijos": pagina_pagos,
    "Gastos variables": pagina_gastos,
}[pagina]()
