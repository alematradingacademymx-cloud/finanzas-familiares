# Finanzas Familiares: guía de instalación

App en Streamlit para registrar ingresos, gastos fijos, pagos y gastos variables, y saber cuánto falta por juntar en cada fecha de pago. Los datos se guardan en el Google Sheet "Finanzas Familiares - Base de datos".

## Archivos

| Archivo | Qué hace |
|---|---|
| `app.py` | Las pantallas: Resumen, Ingresos, Pagos y gastos fijos, Gastos variables |
| `logic.py` | Los cálculos: faltante del mes, saldo, calendario de pagos, generación de pagos |
| `db.py` | Lee y escribe en el Google Sheet |
| `auth.py` | Inicio de sesión y registro con código familiar |
| `.streamlit/secrets.toml.example` | Plantilla de las llaves (credenciales) |

## Paso 1. Crear la cuenta de servicio de Google (una sola vez)

La cuenta de servicio es la llave con la que la app entra a tu hoja.

1. Entra a https://console.cloud.google.com con tu cuenta de Gmail.
2. Arriba, en el selector de proyectos, elige **Nuevo proyecto**. Nómbralo `finanzas-familiares` y créalo.
3. Busca **Google Sheets API** en la barra de búsqueda y dale **Habilitar**. Haz lo mismo con **Google Drive API**.
4. Ve a **IAM y administración > Cuentas de servicio > Crear cuenta de servicio**. Nómbrala `finanzas-app` y dale **Listo** (no necesita roles).
5. Entra a la cuenta que creaste, pestaña **Claves > Agregar clave > Crear clave nueva > JSON**. Se descarga un archivo `.json`. Guárdalo en un lugar seguro y no lo compartas.
6. Abre el JSON y copia el valor de `client_email` (termina en `iam.gserviceaccount.com`).
7. Abre tu Google Sheet, dale **Compartir**, pega ese correo y dale permiso de **Editor**.

## Paso 2. Probar en tu computadora

```bash
cd finanzas-app
pip install -r requirements.txt
```

1. Copia `.streamlit/secrets.toml.example` como `.streamlit/secrets.toml`.
2. Abre el JSON con el Bloc de notas, copia todo su contenido y pégalo dentro de `gcp_json = ''' ... '''`.
3. Cambia `codigo_familia` por un código tuyo.
4. Corre la app:

```bash
streamlit run app.py
```

5. En **Crear cuenta** registra tu usuario con el código familiar.
6. Opcional: en la pestaña **Usuarios** de la hoja cambia tu `rol` a `admin` (servirá en las siguientes fases).

## Paso 3. Publicarla para tu familia

1. Sube la carpeta a un repositorio **privado** de GitHub. El `.gitignore` ya evita que se suban `secrets.toml` y el JSON.
2. Entra a https://share.streamlit.io, dale **Create app**, elige el repositorio y `app.py` como archivo principal.
3. En **Advanced settings > Secrets** pega todo el contenido de tu `secrets.toml`.
4. Dale **Deploy**. Comparte el link y el código familiar con tu familia: cada quien crea su cuenta y solo ve sus propios datos.

## Cómo funciona

- **Gastos fijos:** los registras una vez (renta, internet, tarjeta) con su día de pago y frecuencia. La app crea sola los pagos de este mes y del siguiente en la pestaña Pagos.
- **Pagos:** en "Por pagar" marcas cada pago como pagado, con el monto y la fecha reales. Queda en el historial.
- **Resumen:** muestra lo recibido, lo gastado, lo disponible y cuánto falta por juntar en el mes, contando el ahorro mensual de tus metas activas.
- **Calendario:** ordena los pagos pendientes por fecha y, con tu dinero disponible hoy más los ingresos que esperas antes de cada fecha, te dice si cada pago está cubierto o cuánto falta.

Los datos de ejemplo del usuario `demo` se pueden borrar de la hoja cuando empieces a usarla.

- **Saldo inicial:** al empezar, registra en Ingresos el dinero que ya tienes con el tipo "Saldo inicial", una sola vez.
- **Metas:** crea metas con costo y fecha objetivo, registra aportaciones y ve cuánto apartar al mes.

## Recordatorios por correo y Google Calendar

El archivo `apps_script/Codigo.gs` se instala dentro del Google Sheet:

1. Abre el Google Sheet y ve a **Extensiones > Apps Script**.
2. Borra lo que haya en el editor, pega todo el contenido de `Codigo.gs` y guarda (Ctrl+S).
3. Arriba elige la función **instalar** y dale **Ejecutar**. Autoriza los permisos (correo, calendario y hoja). Si aparece "Google no verificó esta app", da clic en **Configuración avanzada** y luego en **Ir a ... (no seguro)**: es tu propio script.
4. Para probar, ejecuta **probarCorreoDiario**: cada persona recibe sus pagos de los próximos 30 días.

Qué queda programado:

- Todos los días a las 9 a.m.: correo con pagos por vencer (según los días de aviso de cada gasto fijo, el día anterior y el mismo día) y pagos vencidos.
- Los lunes a las 9 a.m.: resumen semanal con lo pagado, lo pendiente, los ingresos por cobrar y las metas.
- Cada hora: los pagos pendientes se agregan al calendario "Finanzas Familiares - Pagos" con invitación al correo de cada persona, y los pagados se marcan en verde.

## Siguiente fase

- Historial con gráficas por mes y por categoría.
