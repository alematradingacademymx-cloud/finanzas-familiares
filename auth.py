"""Inicio de sesión y registro de usuarios."""
from __future__ import annotations

import re
from datetime import date

import bcrypt
import streamlit as st

import db


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verificar(password: str, guardado: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), str(guardado).encode())
    except ValueError:
        return False


def _buscar(usuario: str):
    df = db.leer("Usuarios")
    fila = df[df["usuario"].astype(str).str.lower() == usuario.lower()]
    return None if fila.empty else fila.iloc[0]


def pantalla_acceso() -> None:
    st.title("Finanzas Familiares")
    entrar, registrarse = st.tabs(["Entrar", "Crear cuenta"])

    with entrar:
        with st.form("login"):
            usuario = st.text_input("Usuario").strip()
            password = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", type="primary"):
                u = _buscar(usuario) if usuario else None
                if u is not None and _verificar(password, u["password_hash"]):
                    st.session_state.usuario = str(u["usuario"])
                    st.session_state.nombre = str(u["nombre"]) or str(u["usuario"])
                    st.session_state.rol = str(u["rol"]) or "usuario"
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

    with registrarse:
        st.caption("Pide el código familiar a quien administra la app.")
        with st.form("registro"):
            nombre = st.text_input("Tu nombre").strip()
            usuario = st.text_input("Usuario (sin espacios)").strip().lower()
            correo = st.text_input("Correo (para recordatorios de pago)").strip()
            password = st.text_input("Contraseña (mínimo 6 caracteres)", type="password")
            codigo = st.text_input("Código familiar", type="password")
            if st.form_submit_button("Crear cuenta"):
                if codigo != st.secrets.get("codigo_familia", ""):
                    st.error("El código familiar no es correcto.")
                elif not re.fullmatch(r"[a-z0-9_.]{3,20}", usuario):
                    st.error("El usuario debe tener de 3 a 20 letras, números, punto o guion bajo.")
                elif len(password) < 6:
                    st.error("La contraseña debe tener al menos 6 caracteres.")
                elif "@" not in correo:
                    st.error("Escribe un correo válido.")
                elif _buscar(usuario) is not None:
                    st.error("Ese usuario ya existe.")
                else:
                    db.agregar("Usuarios", [{
                        "usuario": usuario, "nombre": nombre or usuario, "correo": correo,
                        "password_hash": _hash(password), "rol": "usuario",
                        "fecha_alta": date.today().isoformat(),
                    }])
                    st.success("Cuenta creada. Ya puedes entrar en la pestaña Entrar.")


def cerrar_sesion() -> None:
    for k in ("usuario", "nombre", "rol", "pagos_generados"):
        st.session_state.pop(k, None)
    st.rerun()
