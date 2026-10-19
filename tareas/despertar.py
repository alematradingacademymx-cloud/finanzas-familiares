"""Abre la app en un navegador real; si Streamlit Cloud la durmió, la despierta."""
import os
import re
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "https://finanzas-familiares-saludfinanciera.streamlit.app")

with sync_playwright() as p:
    navegador = p.chromium.launch()
    pagina = navegador.new_page()
    pagina.goto(URL, wait_until="domcontentloaded", timeout=90_000)
    pagina.wait_for_timeout(10_000)

    boton = pagina.get_by_role("button", name=re.compile("get this app back up", re.IGNORECASE))
    if boton.count() > 0:
        print("La app estaba dormida. Despertándola...")
        boton.first.click()
        pagina.wait_for_timeout(90_000)  # tiempo para que vuelva a arrancar
        print("Listo, se envió la orden para despertarla.")
    else:
        pagina.wait_for_timeout(20_000)  # mantiene una sesión abierta un momento
        print("La app ya estaba despierta.")

    navegador.close()
sys.exit(0)
