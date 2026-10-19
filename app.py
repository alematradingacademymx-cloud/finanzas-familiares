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
    pagina = st.radio("Menú", ["Resumen", "Ingresos", "Pagos y gastos fijos", "Gastos variables", "Ahorro", "Metas", "Historial"])
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
    if tabla_usuario("Ingresos").empty:
        st.info("**¿Primera vez aquí?** Empieza registrando tu **saldo inicial**: el dinero que tienes hoy, "
                "ya descontado lo que pagaste antes de usar la app. Ve a **Ingresos** y elige el tipo "
                "**Saldo inicial**. Después da de alta tus gastos fijos en **Pagos y gastos fijos**.")
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
    st.caption(f"Dinero disponible hoy (lo recibido menos lo pagado, gastado y lo que guardaste en ahorro y metas): "
               f"{dinero(saldo)} · Tu ahorro: {dinero(logic.saldo_ahorro(t, U))}")
    if cal.empty:
        st.info("No tienes pagos pendientes.")
    else:
        lineas = ["**Próximos pagos**"]
        for _, p in cal.iterrows():
            dias = (p["fecha"] - hoy()).days if isinstance(p["fecha"], date) else None
            cuando = ("hoy" if dias == 0 else "venció" if dias is not None and dias < 0
                      else f"en {dias} días" if dias is not None else "")
            linea = f"- **{p['concepto']}**: {fecha_txt(p['fecha'])} ({cuando}), {dinero(p['monto'])}"
            if p["falta"] > 0:
                linea += f". Te faltan **{dinero(p['falta'])}**"
            lineas.append(linea)
        lineas.append(f"\n**Total por pagar: {dinero(cal['monto'].sum())}**")
        st.info("\n".join(lineas))

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

    st.subheader("Tus pagos fijos")
    comps = tabla_usuario("Compromisos")
    if not comps.empty:
        comps = comps[comps["activo"].apply(logic.es_verdadero)]
    if comps.empty:
        st.info("Aún no tienes gastos fijos activos.")
        return
    comps = comps.assign(monto_n=logic.a_num(comps["monto"]),
                         dia_n=pd.to_numeric(comps["dia_pago"], errors="coerce")).sort_values("dia_n")
    st.dataframe(pd.DataFrame({
        "Pago": comps["concepto"],
        "Se paga": comps.apply(lambda c: f"Día {int(c['dia_n'])} · {c['frecuencia']}"
                               if pd.notna(c["dia_n"]) else c["frecuencia"], axis=1),
        "Monto": comps["monto_n"].apply(dinero),
        "Categoría": comps["categoria"],
    }), hide_index=True)
    mensual = comps.loc[comps["frecuencia"] == "Mensual", "monto_n"].sum()
    st.caption(f"Total de pagos fijos mensuales: {dinero(mensual)}")


def pagina_ingresos() -> None:
    st.title("Ingresos")
    with st.form("nuevo_ingreso", clear_on_submit=True):
        st.subheader("Registrar ingreso")
        c1, c2 = st.columns(2)
        fecha = c1.date_input("Fecha", value=hoy(), format="DD/MM/YYYY")
        monto = c2.number_input("Monto", min_value=0.0, step=100.0, format="%.2f")
        concepto = st.selectbox("Concepto", CAT_INGRESO, accept_new_options=True)
        c3, c4 = st.columns(2)
        tipo = c3.radio("Tipo", ["Fijo", "Variable", "Saldo inicial"], horizontal=True,
                        help="Saldo inicial: el dinero que ya tenías al empezar a usar la app, "
                             "con tus pagos anteriores ya descontados. Regístralo una sola vez.")
        estado = c4.radio("Estado", ["Recibido", "Esperado"], horizontal=True,
                          help="Esperado: aún no te pagan, pero sabes que llegará en esa fecha.")
        notas = st.text_input("Notas (opcional)")
        if st.form_submit_button("Guardar ingreso", type="primary"):
            if tipo == "Saldo inicial":
                estado = "Recibido"
                concepto = "Saldo inicial"
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


def pagina_metas() -> None:
    st.title("Metas de ahorro")
    with st.form("nueva_meta", clear_on_submit=True):
        st.subheader("Nueva meta")
        nombre = st.text_input("¿Para qué quieres ahorrar? (ej. Viaje a Cancún, Fondo de emergencia)")
        c1, c2 = st.columns(2)
        costo = c1.number_input("¿Cuánto necesitas?", min_value=0.0, step=500.0, format="%.2f")
        y, m = hoy().year, hoy().month + 6
        objetivo = c2.date_input("¿Para cuándo?", value=date(y + (m - 1) // 12, (m - 1) % 12 + 1, 1),
                                 min_value=hoy(), format="DD/MM/YYYY")
        c3, c4 = st.columns(2)
        prioridad = c3.selectbox("Prioridad", ["Alta", "Media", "Baja"], index=1)
        incluir = c4.checkbox("Contar su ahorro mensual en el faltante del mes", value=True,
                              help="Si la marcas, el Resumen te dice cuánto juntar para pagar todo y además ahorrar.")
        if st.form_submit_button("Crear meta", type="primary"):
            if not nombre.strip() or costo <= 0:
                st.error("Escribe el nombre de la meta y un monto mayor a cero.")
            else:
                db.agregar("Metas", [{
                    "usuario": U, "nombre": nombre.strip(), "costo": costo,
                    "fecha_objetivo": objetivo.isoformat(), "prioridad": prioridad,
                    "estado": "Activa", "incluir_en_faltante": incluir,
                }])
                st.toast("Meta creada")
                st.rerun()

    metas = logic.metas_usuario(t, U, hoy())
    if metas.empty:
        st.info("Aún no tienes metas. Crea la primera arriba.")
        return

    activas = metas[metas["estado"] == "Activa"]
    if not activas.empty:
        st.caption(f"Para cumplir tus metas activas a tiempo, aparta **{dinero(activas['ahorro_mensual'].sum())}** "
                   f"al mes. Llevas ahorrado **{dinero(metas['actual'].sum())}** en total.")

    orden = {"Activa": 0, "Pausada": 1, "Cumplida": 2}
    metas = metas.assign(_o=metas["estado"].map(orden).fillna(3)).sort_values(["_o", "fecha_objetivo"])
    for _, mt in metas.iterrows():
        with st.container(border=True):
            st.markdown(f"### {mt['nombre']}  \n{mt['estado']} · prioridad {mt['prioridad']} · "
                        f"para el {fecha_txt(mt['fecha_objetivo'])}")
            st.progress(float(mt["avance"]), text=f"{mt['avance']:.0%}: llevas {dinero(mt['actual'])} "
                                                  f"de {dinero(mt['costo'])}")
            if mt["estado"] == "Activa":
                st.markdown(f"Te faltan **{dinero(mt['faltante'])}**. Aparta **{dinero(mt['ahorro_mensual'])} "
                            f"al mes** durante {mt['meses']} {'mes' if mt['meses'] == 1 else 'meses'}.")
            a, b, c = st.columns(3)
            with a.popover("Aportar", disabled=mt["estado"] == "Cumplida"):
                with st.form(f"aportar_{mt['id']}"):
                    monto = st.number_input("Monto", min_value=0.0, step=100.0, format="%.2f")
                    fecha = st.date_input("Fecha", value=hoy(), format="DD/MM/YYYY")
                    if st.form_submit_button("Guardar aportación", type="primary"):
                        if monto <= 0:
                            st.error("Escribe un monto mayor a cero.")
                        else:
                            db.agregar("Aportaciones", [{
                                "usuario": U, "meta_id": mt["id"], "fecha": fecha.isoformat(), "monto": monto,
                            }])
                            if mt["actual"] + monto >= mt["costo"]:
                                db.actualizar("Metas", mt["id"], {"estado": "Cumplida"})
                                st.balloons()
                            st.toast("Aportación guardada")
                            st.rerun()
            if mt["estado"] == "Activa" and b.button("Pausar", key=f"pausa_{mt['id']}"):
                db.actualizar("Metas", mt["id"], {"estado": "Pausada"})
                st.rerun()
            if mt["estado"] == "Pausada" and b.button("Reactivar", key=f"react_{mt['id']}"):
                db.actualizar("Metas", mt["id"], {"estado": "Activa"})
                st.rerun()
            if mt["estado"] != "Cumplida" and c.button("Marcar cumplida", key=f"cumple_{mt['id']}"):
                db.actualizar("Metas", mt["id"], {"estado": "Cumplida"})
                st.rerun()

    apo = tabla_usuario("Aportaciones")
    if not apo.empty:
        with st.expander("Historial de aportaciones"):
            nombres = dict(zip(metas["id"].astype(str), metas["nombre"]))
            st.dataframe(pd.DataFrame({
                "Fecha": apo["fecha"],
                "Meta": apo["meta_id"].astype(str).map(nombres).fillna(apo["meta_id"]),
                "Monto": logic.a_num(apo["monto"]).apply(dinero),
            }).sort_values("Fecha", ascending=False), hide_index=True)


AZUL, NARANJA, AQUA = "#3987e5", "#d95926", "#199e70"


def pagina_ahorro() -> None:
    st.title("Ahorro")
    total = logic.saldo_ahorro(t, U)
    disponible = logic.saldo_actual(t, U)
    c1, c2 = st.columns(2)
    c1.metric("Tu ahorro", dinero(total))
    c2.metric("Dinero disponible", dinero(disponible))
    st.caption("Al agregar ahorro, ese dinero sale de tu disponible y queda guardado aquí. "
               "Al retirarlo, regresa a tu disponible. Es aparte de tus metas.")

    agregar, retirar = st.columns(2)
    with agregar.form("deposito", clear_on_submit=True):
        st.subheader("Agregar ahorro")
        monto = st.number_input("Monto", min_value=0.0, step=100.0, format="%.2f", key="dep_monto")
        fecha = st.date_input("Fecha", value=hoy(), format="DD/MM/YYYY", key="dep_fecha")
        nota = st.text_input("Nota (opcional)", key="dep_nota")
        if st.form_submit_button("Agregar", type="primary"):
            if monto <= 0:
                st.error("Escribe un monto mayor a cero.")
            else:
                db.agregar("Ahorro", [{"usuario": U, "fecha": fecha.isoformat(), "tipo": "Depósito",
                                       "monto": monto, "notas": nota}])
                st.toast(f"Agregaste {dinero(monto)} a tu ahorro")
                st.rerun()
    with retirar.form("retiro", clear_on_submit=True):
        st.subheader("Descontar ahorro")
        monto = st.number_input("Monto", min_value=0.0, step=100.0, format="%.2f", key="ret_monto")
        fecha = st.date_input("Fecha", value=hoy(), format="DD/MM/YYYY", key="ret_fecha")
        nota = st.text_input("¿Para qué lo usaste? (opcional)", key="ret_nota")
        if st.form_submit_button("Descontar"):
            if monto <= 0:
                st.error("Escribe un monto mayor a cero.")
            elif monto > total + 0.005:
                st.error(f"No puedes descontar más de lo que tienes ahorrado ({dinero(total)}).")
            else:
                db.agregar("Ahorro", [{"usuario": U, "fecha": fecha.isoformat(), "tipo": "Retiro",
                                       "monto": monto, "notas": nota}])
                st.toast(f"Descontaste {dinero(monto)} de tu ahorro")
                st.rerun()

    mov = logic.movimientos_ahorro(t, U)
    if mov.empty:
        st.info("Aún no tienes movimientos de ahorro.")
        return
    mov = mov.assign(saldo=mov["con_signo"].cumsum())
    st.subheader("Cómo ha crecido tu ahorro")
    serie = mov.dropna(subset=["fecha"]).groupby("fecha")["saldo"].last()
    serie.index = pd.to_datetime(serie.index)
    st.line_chart(serie.rename("Ahorro"), color=AZUL, x_label="", y_label="Ahorro ($)")
    st.subheader("Movimientos")
    st.dataframe(pd.DataFrame({
        "Fecha": mov["fecha"].apply(fecha_txt),
        "Movimiento": mov["tipo"],
        "Monto": mov["con_signo"].apply(lambda x: ("+" if x >= 0 else "-") + dinero(abs(x))),
        "Saldo": mov["saldo"].apply(dinero),
        "Nota": mov["notas"],
    }).iloc[::-1], hide_index=True)


def pagina_historial() -> None:
    st.title("Historial")
    actual = logic.mes_de(hoy())
    n = st.radio("Periodo", [3, 6, 12], index=1, horizontal=True, format_func=lambda x: f"Últimos {x} meses")
    meses = logic.ultimos_meses(actual, n)
    h = logic.historial_mensual(t, U, meses)
    if h[["ingresos", "gastos", "a_ahorro", "a_metas"]].abs().sum().sum() == 0:
        st.info("Aún no hay movimientos en este periodo. Conforme registres ingresos, pagos y gastos, "
                "aquí verás cómo cambian mes a mes.")
        return

    etiquetas = [nombre_mes(m) for m in meses]
    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos del periodo", dinero(h["ingresos"].sum()))
    c2.metric("Gastos del periodo", dinero(h["gastos"].sum()))
    c3.metric("Balance", dinero(h["balance"].sum()))
    st.caption("Los ingresos no incluyen tu saldo inicial. Los gastos son pagos fijos pagados más gastos variables.")

    st.subheader("Ingresos y gastos por mes")
    barras = pd.DataFrame({"Ingresos": h["ingresos"].values, "Gastos": h["gastos"].values},
                          index=pd.Index(meses, name="Mes"))
    st.bar_chart(barras, stack=False, color=[AZUL, NARANJA], x_label="", y_label="Monto ($)")

    st.subheader("¿En qué se va tu dinero?")
    opciones = ["Todo el periodo"] + meses[::-1]
    elegido = st.selectbox("Mes", opciones, format_func=lambda m: m if m == "Todo el periodo" else nombre_mes(m))
    cats = logic.gastos_por_categoria(t, U, meses if elegido == "Todo el periodo" else [elegido])
    if cats.empty:
        st.info("No hay gastos registrados en ese periodo.")
    else:
        st.bar_chart(cats.rename("Gastado"), horizontal=True, color=AZUL, x_label="Monto ($)", y_label="")
        st.dataframe(pd.DataFrame({
            "Categoría": cats.index, "Gastado": cats.apply(dinero).values,
            "% del total": (cats / cats.sum()).apply(lambda x: f"{x:.0%}").values,
        }), hide_index=True)

    acum = logic.ahorro_acumulado(t, U, meses)
    if acum.abs().sum().sum() > 0:
        st.subheader("Ahorro acumulado")
        acum.index = pd.Index(meses, name="Mes")
        st.line_chart(acum, color=[AZUL, AQUA], x_label="", y_label="Monto ($)")
        st.caption("Ahorro: tu ahorro libre al cierre de cada mes. Metas: lo aportado a tus metas hasta ese mes.")

    st.subheader("Detalle por mes")
    st.dataframe(pd.DataFrame({
        "Mes": etiquetas,
        "Ingresos": h["ingresos"].apply(dinero).values,
        "Pagos fijos": h["pagos_fijos"].apply(dinero).values,
        "Gastos variables": h["gastos_variables"].apply(dinero).values,
        "Balance": h["balance"].apply(dinero).values,
        "A ahorro": h["a_ahorro"].apply(dinero).values,
        "A metas": h["a_metas"].apply(dinero).values,
    }).iloc[::-1], hide_index=True)


{
    "Resumen": pagina_resumen,
    "Ingresos": pagina_ingresos,
    "Pagos y gastos fijos": pagina_pagos,
    "Gastos variables": pagina_gastos,
    "Ahorro": pagina_ahorro,
    "Metas": pagina_metas,
    "Historial": pagina_historial,
}[pagina]()
