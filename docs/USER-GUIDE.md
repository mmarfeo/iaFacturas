# IAFacturas — Guía de Usuario

> Versión: 1.0 · Última actualización: 24 de Abril 2026

---

## ¿Qué es IAFacturas?

**IAFacturas** es una aplicación web que extrae y valida automáticamente los datos de tus facturas electrónicas AFIP. Subís el PDF de una factura, y el sistema te devuelve:

- CUIT del emisor y receptor
- CAE y su estado de vigencia
- Fecha de vencimiento del CAE
- Importe total
- Fecha de emisión
- Razón social del emisor
- Tipo de comprobante y número

Todo sin necesidad de tipear nada a mano.

---

## Acceso

- **URL:** `https://iafacturas.dewoc.com`
- El sistema funciona desde cualquier navegador moderno (Chrome, Firefox, Edge, Safari)
- No requiere instalación de ningún software

---

## 1. Crear una cuenta

1. Ingresá a `https://iafacturas.dewoc.com/auth/register`
2. Completá los campos:
   - **Nombre:** Tu nombre completo
   - **Email:** El email que usarás para ingresar
   - **Contraseña:** Mínimo 6 caracteres
   - **Plan:** Elegí entre Free o Pro (podés cambiarlo después)
3. Hacé clic en **Crear cuenta**
4. Serás redirigido automáticamente al dashboard

> **Nota:** No se envía email de verificación en esta versión. El acceso es inmediato.

---

## 2. Iniciar sesión

1. Ingresá a `https://iafacturas.dewoc.com/auth/login`
2. Completá email y contraseña
3. Hacé clic en **Ingresar**

La sesión dura 7 días. Al vencerse, el sistema te pedirá que inicies sesión nuevamente.

Para cerrar sesión hacé clic en tu nombre en la barra superior → **Cerrar sesión**.

---

## 3. Dashboard

Al ingresar, el dashboard muestra:

| Sección | Qué muestra |
|---|---|
| **Facturas este mes** | Total de facturas procesadas en el mes actual |
| **CAE Vigentes** | Cantidad de facturas con CAE válido (entre las últimas 5) |
| **CAE Vencidos** | Cantidad de facturas con CAE vencido (entre las últimas 5) |
| **Últimas facturas** | Tabla con las 5 facturas más recientes |
| **Panel lateral** | Plan actual, uso del mes y accesos rápidos |

---

## 4. Subir una factura

### Pasos

1. Hacé clic en **Subir Factura** en el menú o en el dashboard
2. Arrastrá el archivo PDF a la zona de carga, o hacé clic en **Seleccionar archivo**
3. El archivo se sube automáticamente al soltarlo / seleccionarlo
4. Aparece una barra de progreso con los pasos del procesamiento:

| Paso | Descripción |
|---|---|
| 0 | Extrayendo texto del PDF (OCR) |
| 1 | Aplicando reconocimiento de campos AFIP |
| 2 | Validando CAE |
| 3 | Procesando con IA (si el paso anterior fue insuficiente) |
| 4 | Guardando resultado |

5. Al finalizar, serás redirigido automáticamente a la página de resultado

### Formatos aceptados

- **PDF** (recomendado)
- PDFs nativos (con texto seleccionable): extracción más rápida y precisa
- PDFs escaneados (imágenes): el sistema aplica OCR automáticamente, puede tardar más

### Límites por plan

| Plan | Facturas por mes |
|---|---|
| **Free** | 10 facturas |
| **Pro** | Ilimitadas |

Al alcanzar el límite del plan Free, el sistema mostrará un mensaje de error hasta el próximo mes.

---

## 5. Ver el resultado de una factura

Después del procesamiento, o desde el historial, podés ver el detalle completo:

### Encabezado

- **Badge CAE VIGENTE** (verde): el CAE es válido y no venció
- **Badge CAE VENCIDO** (rojo): el CAE está vencido o no se encontró

### Pestañas

#### Pestaña "Datos"

Muestra los campos extraídos en formato tabla:

| Campo | Descripción |
|---|---|
| CAE | Código de Autorización Electrónica |
| Vencimiento CAE | Fecha hasta la que el CAE es válido |
| CUIT Emisor | CUIT del emisor de la factura |
| CUIT Receptor | CUIT del receptor |
| Importe Total | Monto total de la factura |
| Fecha Factura | Fecha de emisión |
| Tipo Comprobante | Ej: Factura A, Factura B, etc. |
| Razón Social | Nombre del emisor |

#### Pestaña "JSON"

Muestra todos los datos en formato JSON (útil para integraciones). Incluye un botón **Copiar** para copiar el JSON al portapapeles.

### Acciones disponibles

- **Descargar Excel**: descarga los campos principales en un archivo `.xlsx`
- **Volver al historial**: regresa a la lista de facturas

---

## 6. Historial de facturas

Ingresá desde el menú → **Historial**.

### Filtros disponibles

- **Búsqueda por texto**: filtra por nombre de archivo o CUIT del emisor
- **Estado CAE**: todos / vigente / vencido

### Paginación

Se muestran 15 facturas por página. Usá los botones de navegación al final de la tabla.

### Exportar historial

Hacé clic en **Exportar Excel** para descargar todas las facturas del historial (con los filtros aplicados) en un archivo `.xlsx` con columnas: Archivo, CUIT Emisor, Importe, Fecha, CAE, Estado CAE.

---

## 7. Planes

Ingresá desde el menú → **Planes** o desde el banner en el dashboard.

| Plan | Precio | Facturas/mes | Descripción |
|---|---|---|---|
| **Free** | $0 | 10 | Ideal para probar el servicio |
| **Pro** | $9.990/mes | Ilimitadas | Para uso profesional o empresas |
| **Empresa** | A consultar | Ilimitadas + API | Integración directa vía API |

> **Nota:** El pago online está en desarrollo. Por ahora, para contratar el plan Pro contactá a soporte.

---

## 8. Preguntas frecuentes

**¿Qué pasa si la factura es escaneada?**
El sistema detecta automáticamente si el PDF no tiene texto seleccionable y aplica OCR. El procesamiento puede tardar unos segundos más, pero el resultado es el mismo.

**¿Qué pasa si el sistema no encuentra algún campo?**
Si el OCR y los patrones de reconocimiento no logran extraer un campo con suficiente confianza, el sistema recurre a un modelo de IA (LLM) para completar los datos faltantes.

**¿Los archivos PDF se almacenan permanentemente?**
Los archivos subidos se guardan en el servidor para referencia futura. Si necesitás que se eliminen, contactá a soporte.

**¿Se puede usar con facturas de cualquier tipo (A, B, C, M)?**
Sí. El sistema reconoce todos los tipos de comprobantes AFIP.

**¿La validación del CAE es en tiempo real?**
En esta versión, la validación es provisional: verifica que el campo CAE esté presente en el documento. La validación online contra los servidores de AFIP está planificada para la próxima versión.

**¿Puedo exportar varias facturas a la vez?**
Sí, desde el Historial podés exportar todas las facturas (o las que pasen el filtro activo) a un Excel con un solo clic.

**¿Cómo cambio mi contraseña?**
La funcionalidad de cambio de contraseña está en desarrollo. Por ahora, contactá a soporte.

---

## 9. Soporte

Para consultas o problemas:
- **Email:** soporte@dewoc.com
- **Web:** `https://dewoc.com`

---

*IAFacturas — Dewoc · 2026*
