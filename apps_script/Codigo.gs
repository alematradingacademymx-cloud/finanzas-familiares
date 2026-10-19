/**
 * Finanzas Familiares: recordatorios por correo y eventos en Google Calendar.
 *
 * Se pega en el Google Sheet: Extensiones > Apps Script.
 * Después se ejecuta UNA vez la función `instalar` y se autoriza.
 *
 * Qué hace:
 *  - Todos los días a las 9 a.m.: correo a cada persona con los pagos por vencer y los vencidos.
 *  - Los lunes a las 9 a.m.: resumen semanal (lo pagado, lo pendiente, metas).
 *  - Cada hora: crea en Google Calendar los pagos pendientes nuevos y marca los ya pagados.
 */

const CONFIG = {
  ZONA: 'America/Mexico_City',
  HORA_CORREO: 9,
  DIA_RESUMEN: ScriptApp.WeekDay.MONDAY,
  CALENDARIO: 'Finanzas Familiares - Pagos',
  APP_URL: 'https://finanzas-familiares-saludfinanciera.streamlit.app',
  DIAS_PROXIMOS: 30,
};

// ---------------------------------------------------------------- instalación

function instalar() {
  const funciones = ['revisionDiaria', 'resumenSemanal', 'sincronizarCalendario'];
  ScriptApp.getProjectTriggers()
    .filter(t => funciones.indexOf(t.getHandlerFunction()) >= 0)
    .forEach(t => ScriptApp.deleteTrigger(t));

  ScriptApp.newTrigger('revisionDiaria').timeBased()
    .everyDays(1).atHour(CONFIG.HORA_CORREO).inTimezone(CONFIG.ZONA).create();
  ScriptApp.newTrigger('resumenSemanal').timeBased()
    .onWeekDay(CONFIG.DIA_RESUMEN).atHour(CONFIG.HORA_CORREO).inTimezone(CONFIG.ZONA).create();
  ScriptApp.newTrigger('sincronizarCalendario').timeBased().everyHours(1).create();

  sincronizarCalendario();
  Logger.log('Listo: recordatorios diarios, resumen de los lunes y calendario instalados.');
}

/** Manda ahora mismo a cada persona el correo diario con sus pagos de los próximos 30 días (para probar). */
function probarCorreoDiario() {
  enviarCorreosDiarios_(true);
}

/** Manda ahora mismo el resumen semanal (para probar). */
function probarResumenSemanal() {
  resumenSemanal();
}

// ---------------------------------------------------------------- tareas programadas

function revisionDiaria() {
  sincronizarCalendario();
  enviarCorreosDiarios_(false);
}

function enviarCorreosDiarios_(forzar) {
  const d = leerTodo_();
  const hoy = diaNum_(new Date());
  usuariosConCorreo_(d).forEach(u => {
    const cal = calendario_(d, u.usuario, hoy);
    const saldo = saldo_(d, u.usuario);
    const vencidos = cal.filter(p => p.dias < 0);
    const porVencer = cal.filter(p => {
      if (p.dias < 0) return false;
      if (forzar) return p.dias <= CONFIG.DIAS_PROXIMOS;
      return p.dias === p.aviso || p.dias <= 1;
    });
    if (!vencidos.length && !porVencer.length) return;

    let html = encabezado_(`Hola, ${u.nombre}`);
    html += disponibleOculto_(saldo);
    if (vencidos.length) {
      html += `<h3 style="color:#C00000;margin-bottom:4px">Pagos vencidos</h3>`;
      html += `<p style="margin-top:0">Ya pasó su fecha y no están marcados como pagados.</p>`;
      html += tablaPagos_(vencidos);
    }
    if (porVencer.length) {
      html += `<h3 style="margin-bottom:4px">Pagos por vencer</h3>`;
      html += tablaPagos_(porVencer);
    }
    const falta = Math.max(0, ...vencidos.concat(porVencer).map(p => p.falta));
    html += falta > 0
      ? `<p style="color:#C00000"><b>Te faltan ${dinero_(falta)} para cubrir estos pagos.</b></p>`
      : `<p style="color:#2E7D32"><b>Con tu dinero disponible cubres estos pagos.</b></p>`;
    html += pie_();

    const asunto = vencidos.length
      ? `Tienes ${vencidos.length} pago(s) vencido(s)`
      : `Pagos por vencer: ${porVencer.map(p => p.concepto).join(', ')}`;
    MailApp.sendEmail({ to: u.correo, subject: `Finanzas Familiares: ${asunto}`, htmlBody: html });
  });
}

function resumenSemanal() {
  const d = leerTodo_();
  const hoy = diaNum_(new Date());
  usuariosConCorreo_(d).forEach(u => {
    const saldo = saldo_(d, u.usuario);
    const pagados = d.Pagos.filter(p => p.usuario === u.usuario && p.estado === 'Pagado'
      && p.fecha_pago && hoy - diaNum_(p.fecha_pago) <= 7 && hoy - diaNum_(p.fecha_pago) >= 0);
    const proximos = calendario_(d, u.usuario, hoy).filter(p => p.dias <= CONFIG.DIAS_PROXIMOS);
    const esperados = d.Ingresos.filter(i => i.usuario === u.usuario && i.estado === 'Esperado');
    const metas = metas_(d, u.usuario, hoy).filter(m => m.estado === 'Activa');

    let html = encabezado_(`Tu semana, ${u.nombre}`);
    html += disponibleOculto_(saldo);

    html += `<h3 style="margin-bottom:4px">Pagado en los últimos 7 días</h3>`;
    html += pagados.length
      ? lista_(pagados.map(p => `${p.concepto}: ${dinero_(num_(p.monto_pagado))} (${fechaTxt_(p.fecha_pago)})`))
      : `<p style="margin-top:0">Nada registrado.</p>`;

    html += `<h3 style="margin-bottom:4px">Pagos de los próximos ${CONFIG.DIAS_PROXIMOS} días</h3>`;
    html += proximos.length ? tablaPagos_(proximos) : `<p style="margin-top:0">No tienes pagos pendientes.</p>`;

    if (esperados.length) {
      html += `<h3 style="margin-bottom:4px">Ingresos por cobrar</h3>`;
      html += lista_(esperados.map(i => `${i.concepto}: ${dinero_(num_(i.monto))} (${fechaTxt_(i.fecha)})`));
    }
    if (metas.length) {
      html += `<h3 style="margin-bottom:4px">Metas de ahorro</h3>`;
      html += lista_(metas.map(m =>
        `${m.nombre}: ${Math.round(m.avance * 100)}% (${dinero_(m.actual)} de ${dinero_(m.costo)}). ` +
        `Aparta ${dinero_(m.ahorroMensual)} al mes.`));
    }
    html += pie_();
    MailApp.sendEmail({ to: u.correo, subject: 'Finanzas Familiares: tu resumen semanal', htmlBody: html });
  });
}

function sincronizarCalendario() {
  const d = leerTodo_();
  const hoy = diaNum_(new Date());
  const cal = calendarioGoogle_();
  const dueno = Session.getEffectiveUser().getEmail().toLowerCase();
  const hoja = SpreadsheetApp.getActive().getSheetByName('Pagos');
  const correos = {};
  d.Usuarios.forEach(u => { correos[u.usuario] = String(u.correo || '').trim(); });
  const avisos = {};
  d.Compromisos.forEach(c => { avisos[c.id] = num_(c.recordatorio_dias) || 3; });

  d.Pagos.forEach(p => {
    if (!p.fecha_vencimiento) return;
    const idEvento = String(p.evento_calendario_id || '');
    const titulo = `Pago: ${p.concepto} ${dinero_(num_(p.monto))}`;

    if (p.estado === 'Pendiente' && !idEvento && diaNum_(p.fecha_vencimiento) >= hoy) {
      const correo = correos[p.usuario];
      const opciones = { description: `Pago de ${p.usuario} registrado en Finanzas Familiares.\n${CONFIG.APP_URL}` };
      if (correo && correo.toLowerCase() !== dueno) {
        opciones.guests = correo;
        opciones.sendInvites = true;
      }
      const ev = cal.createAllDayEvent(titulo, aFecha_(p.fecha_vencimiento), opciones);
      ev.removeAllReminders();
      const dias = avisos[p.compromiso_id] || 3;
      ev.addPopupReminder(Math.max(0, dias * 1440 - CONFIG.HORA_CORREO * 60)); // 9 a.m. N días antes
      ev.addPopupReminder(1440 - CONFIG.HORA_CORREO * 60);                      // 9 a.m. el día anterior
      hoja.getRange(p._fila, 11).setValue(ev.getId());
    } else if (p.estado === 'Pagado' && idEvento) {
      const ev = cal.getEventById(idEvento);
      if (ev && ev.getTitle().indexOf('[Pagado]') !== 0) {
        ev.setTitle(`[Pagado] ${titulo}`);
        ev.setColor(CalendarApp.EventColor.GREEN);
        ev.removeAllReminders();
      }
    }
  });
}

// ---------------------------------------------------------------- cálculos

/** Pagos pendientes en orden de fecha, con acumulado y cuánto falta (misma lógica que la app). */
function calendario_(d, usuario, hoy) {
  const saldo = saldo_(d, usuario);
  const esperados = d.Ingresos.filter(i => i.usuario === usuario && i.estado === 'Esperado' && i.fecha);
  const avisos = {};
  d.Compromisos.forEach(c => { avisos[c.id] = num_(c.recordatorio_dias) || 3; });

  const pend = d.Pagos
    .filter(p => p.usuario === usuario && p.estado === 'Pendiente' && p.fecha_vencimiento)
    .map(p => ({ id: p.id, concepto: p.concepto, monto: num_(p.monto), dia: diaNum_(p.fecha_vencimiento),
                 fecha: p.fecha_vencimiento, aviso: avisos[p.compromiso_id] || 3 }))
    .sort((a, b) => a.dia - b.dia);

  let acumulado = 0;
  return pend.map(p => {
    acumulado += p.monto;
    const llega = esperados.filter(i => diaNum_(i.fecha) <= p.dia).reduce((s, i) => s + num_(i.monto), 0);
    const falta = Math.max(0, acumulado - saldo - llega);
    return Object.assign(p, { dias: p.dia - hoy, acumulado: acumulado, falta: falta,
                              cubreConEsperado: falta === 0 && saldo < acumulado });
  });
}

function saldo_(d, usuario) {
  const suma = (filas, col) => filas.reduce((s, f) => s + num_(f[col]), 0);
  const recibido = suma(d.Ingresos.filter(i => i.usuario === usuario && i.estado === 'Recibido'), 'monto');
  const pagado = suma(d.Pagos.filter(p => p.usuario === usuario && p.estado === 'Pagado'), 'monto_pagado');
  const gastado = suma(d.Gastos_Variables.filter(g => g.usuario === usuario), 'monto');
  const apartado = suma(d.Aportaciones.filter(a => a.usuario === usuario), 'monto');
  const ahorro = (d.Ahorro || []).filter(a => a.usuario === usuario)
    .reduce((s, a) => s + (a.tipo === 'Retiro' ? -1 : 1) * num_(a.monto), 0);
  return recibido - pagado - gastado - apartado - ahorro;
}

function metas_(d, usuario, hoy) {
  const hoyF = new Date(hoy * 86400000);
  return d.Metas.filter(m => m.usuario === usuario).map(m => {
    const actual = d.Aportaciones.filter(a => a.meta_id === m.id).reduce((s, a) => s + num_(a.monto), 0);
    const costo = num_(m.costo);
    const faltante = Math.max(0, costo - actual);
    const obj = m.fecha_objetivo ? new Date(diaNum_(m.fecha_objetivo) * 86400000) : hoyF;
    const meses = Math.max(1, (obj.getUTCFullYear() - hoyF.getUTCFullYear()) * 12
                              + obj.getUTCMonth() - hoyF.getUTCMonth());
    return { nombre: m.nombre, estado: m.estado || 'Activa', costo: costo, actual: actual,
             avance: costo ? Math.min(1, actual / costo) : 0, ahorroMensual: faltante / meses };
  });
}

// ---------------------------------------------------------------- lectura de la hoja

function leerTodo_() {
  const libro = SpreadsheetApp.getActive();
  const d = {};
  ['Usuarios', 'Ingresos', 'Compromisos', 'Pagos', 'Gastos_Variables', 'Metas', 'Aportaciones', 'Ahorro']
    .forEach(nombre => {
      const hoja = libro.getSheetByName(nombre);
      if (!hoja) { d[nombre] = []; return; }
      const valores = hoja.getDataRange().getValues();
      const enc = valores[0].map(String);
      d[nombre] = valores.slice(1)
        .map((fila, i) => {
          const o = { _fila: i + 2 };
          enc.forEach((c, j) => { o[c] = fila[j]; });
          return o;
        })
        .filter(o => String(o[enc[0]]).trim() !== '');
    });
  return d;
}

function usuariosConCorreo_(d) {
  return d.Usuarios
    .filter(u => String(u.correo || '').indexOf('@') > 0)
    .map(u => ({ usuario: String(u.usuario), nombre: String(u.nombre || u.usuario), correo: String(u.correo).trim() }));
}

function calendarioGoogle_() {
  const existentes = CalendarApp.getCalendarsByName(CONFIG.CALENDARIO);
  return existentes.length ? existentes[0]
    : CalendarApp.createCalendar(CONFIG.CALENDARIO, { color: CalendarApp.Color.TURQUOISE, timeZone: CONFIG.ZONA });
}

// ---------------------------------------------------------------- utilidades

/** Número de día (días desde 1970) de una fecha de la hoja o un texto yyyy-mm-dd, en hora de México. */
function diaNum_(v) {
  const txt = v instanceof Date ? Utilities.formatDate(v, CONFIG.ZONA, 'yyyy-MM-dd') : String(v).slice(0, 10);
  const [y, m, dd] = txt.split('-').map(Number);
  return Math.round(Date.UTC(y, m - 1, dd) / 86400000);
}

function aFecha_(v) {
  const n = diaNum_(v);
  const u = new Date(n * 86400000);
  return new Date(u.getUTCFullYear(), u.getUTCMonth(), u.getUTCDate());
}

function fechaTxt_(v) {
  const u = new Date(diaNum_(v) * 86400000);
  const meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  return `${u.getUTCDate()} ${meses[u.getUTCMonth()]}`;
}

function num_(v) {
  const n = typeof v === 'number' ? v : parseFloat(String(v).replace(/[$,\s]/g, ''));
  return isNaN(n) ? 0 : n;
}

function dinero_(n) {
  const partes = Math.abs(n).toFixed(2).split('.');
  partes[0] = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return (n < 0 ? '-$' : '$') + partes.join('.');
}

/** Muestra solo los últimos 2 dígitos del monto: $11,140.00 -> $****40. */
function oculto_(n) {
  const entero = String(Math.floor(Math.abs(n)));
  return (n < 0 ? '-$' : '$') + '****' + entero.slice(-2);
}

function disponibleOculto_(saldo) {
  return `<p>Dinero disponible hoy: <b>${oculto_(saldo)}</b><br>` +
    `<span style="color:#888;font-size:12px">Por seguridad ocultamos tu saldo. ` +
    `Consulta el monto completo en la <a href="${CONFIG.APP_URL}">app</a>.</span></p>`;
}

function cuando_(dias) {
  if (dias < 0) return `venció hace ${-dias} día(s)`;
  if (dias === 0) return 'hoy';
  if (dias === 1) return 'mañana';
  return `en ${dias} días`;
}

function tablaPagos_(pagos) {
  const td = 'style="padding:6px 10px;border-bottom:1px solid #ddd"';
  let h = `<table style="border-collapse:collapse;font-family:Arial;font-size:14px">` +
    `<tr style="background:#1F3864;color:#fff"><th ${td}>Pago</th><th ${td}>Fecha</th>` +
    `<th ${td}>Monto</th><th ${td}>Estado</th></tr>`;
  pagos.forEach(p => {
    const estado = p.falta > 0 ? `<span style="color:#C00000">Faltan ${dinero_(p.falta)}</span>`
      : p.cubreConEsperado ? 'Cubierto con ingreso por cobrar' : '<span style="color:#2E7D32">Cubierto</span>';
    h += `<tr><td ${td}>${p.concepto}</td><td ${td}>${fechaTxt_(p.fecha)} (${cuando_(p.dias)})</td>` +
      `<td ${td}>${dinero_(p.monto)}</td><td ${td}>${estado}</td></tr>`;
  });
  return h + '</table>';
}

function lista_(items) {
  return '<ul style="margin-top:0">' + items.map(i => `<li>${i}</li>`).join('') + '</ul>';
}

function encabezado_(titulo) {
  return `<div style="font-family:Arial;font-size:14px;color:#222;max-width:600px">` +
    `<h2 style="color:#1F3864">${titulo}</h2>`;
}

function pie_() {
  return `<p style="margin-top:24px"><a href="${CONFIG.APP_URL}">Abrir Finanzas Familiares</a></p>` +
    `<p style="color:#888;font-size:12px">Correo automático de Finanzas Familiares.</p></div>`;
}
