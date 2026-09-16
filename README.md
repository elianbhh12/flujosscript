# Pipeline Dynamo — config-control / text-analyzer / events-manager (UDZ)

Herramienta para descargar, comparar y auditar la configuración de flujos de
procesamiento de documentos que vive en DynamoDB, y entregar un **Excel
único y presentable** con el inventario actualizado.

---

## 1. ¿Qué hace este proyecto?

Trabaja sobre 3 tablas DynamoDB (una por ambiente: `qa`, `pdn`, `dev`):

| Tabla | Qué contiene |
|---|---|
| **config-control** | La configuración de cada flujo (R2 / R3) — qué pasos ejecuta cada tipo de documento |
| **text-analyzer** | Los "use case" configurados en el servicio de IA que analiza texto |
| **events-manager (UDZ)** | Eventos de `crudos` (datos originales) y `resultados` (transmisiones) |

Con esos datos, responde preguntas como:
- ¿Qué flujos R3 **no tienen** configurado un use case en text-analyzer?
- ¿Hay **subtipos de documento duplicados** entre distintos flujos?
- ¿Qué flujos tienen **transmisiones** además de los datos crudos?
- ¿Qué flujos son **nuevos** desde la última vez que se catalogó todo?

Todo esto se entrega en **un solo archivo Excel** (`reporte_completo.xlsx`),
listo para revisar sin abrir CSVs sueltos.

---

## 2. Requisitos

- **Python 3.9 o superior**
- Paquetes: `boto3` (acceso a AWS/DynamoDB) y `openpyxl` (generar el Excel)
- Credenciales de AWS con permiso de lectura (`Scan`, `DescribeTable`) sobre
  las tablas DynamoDB del proyecto

Instalar dependencias (solo la primera vez, o si aparece un error de
módulo faltante):

```powershell
pip install -r requirements.txt
```

Para correr los tests además de lo anterior:

```powershell
pip install -r requirements-dev.txt
```

---

## 3. Cómo ejecutar

### Opción A — Doble clic (la más fácil)

Haz doble clic en **`ejecutar_pipeline.bat`** (en la raíz del proyecto).
Ese script:
1. Se ubica solo en la carpeta correcta.
2. Revisa que `python` esté instalado.
3. Revisa que `boto3`/`openpyxl` estén instalados; si faltan, los instala solo.
4. Abre el menú interactivo.
5. Al terminar, deja la ventana abierta para que puedas leer el resultado.

### Opción B — Desde una terminal, menú interactivo

```powershell
cd "D:\Elian\Proyectos\Script Banco\flujosscript"
python -m python_pipeline.cli
```

Te muestra un menú y te va preguntando lo necesario en cada paso (ambiente,
credenciales, rutas — con valores por defecto sugeridos automáticamente).

### Opción C — Comandos directos (para automatizar / expertos)

```powershell
# Pipeline completo (descarga + análisis + Excel), sin preguntas:
python -m python_pipeline.cli run-all --env qa --credenciales-file aws_credentials.json

# Solo descargar una tabla:
python -m python_pipeline.cli descargar --env qa --tabla text-analyzer --dry-run

# Pasos individuales (para reprocesar sin volver a descargar):
python -m python_pipeline.cli comparar --r3-dir X --ta-dir Y --out-dir Z
python -m python_pipeline.cli verificar --r3-dir X --out-txt salida.txt
python -m python_pipeline.cli agrupar --r3-dir X --detalle-csv D --out-csv salida.csv
python -m python_pipeline.cli validar-nuevos --r3-dir X --out-csv salida.csv
python -m python_pipeline.cli identificar-eventos --events-dir X --out-csv salida.csv
```

Cada subcomando tiene ayuda propia: `python -m python_pipeline.cli <comando> --help`.

### Instalarlo como comando corto (opcional)

```powershell
pip install -e .
aid-pipeline          # equivalente a "python -m python_pipeline.cli"
```

---

## 4. El menú interactivo, opción por opción

```
1) Descargar una tabla
2) Ejecutar pipeline completo (descarga + analisis + Excel final)
3) Comparar R3 vs Text Analyzer
4) Verificar subtipos repetidos
5) Agrupar reporte por subtipos
6) Validar nuevos R3 vs Orden_RE_Base.txt
7) Identificar eventos UDZ (crudos / transmisiones)
0) Salir
```

| # | Qué hace | Cuándo usarla |
|---|---|---|
| **1** | Descarga una sola tabla (config-control, text-analyzer o events-manager) | Para revisar una tabla puntual sin correr todo |
| **2** | El flujo completo: descarga las 3 tablas, compara, verifica, agrupa y genera el Excel final | **La que usas normalmente** |
| **3** | Cruza `use_case` (R3) contra `cu_name` (Text Analyzer) | Reprocesar sin volver a descargar |
| **4** | Detecta `tipoDocumento` usado por más de un flujo | Revisión puntual |
| **5** | Genera el reporte agrupado por subtipo | Reprocesar sin correr todo el pipeline |
| **6** | Compara los flujos R3 contra el catálogo base (`Orden_RE_Base.txt`) | Cuando tengas ese archivo listo |
| **7** | Por cada flujo UDZ, dice si tiene crudos, transmisiones, o ambos | Auditoría específica de events-manager |

Las opciones 3-7 **autodetectan la última descarga** de cada tabla y la
sugieren como valor por defecto — solo presiona Enter si es la que quieres.

---

## 5. Los 6 pasos del pipeline completo (opción 2)

1. **Descarga** las 3 tablas de DynamoDB (paralelo automático según el
   tamaño de cada tabla) y las clasifica en carpetas.
2. **Compara** R3 (config-control) vs Text Analyzer, por `use_case`/`cu_name`.
3. **Verifica repetidos**: subtipos de documento usados por más de un flujo.
4. **Agrupa**: una fila por JSON, con el subtipo/cantidad agrupados
   visualmente, y la columna **Transmisiones** (Si/No) cruzada contra
   events-manager.
5. **Compara contra el catálogo** (`Orden_RE_Base.txt`) para detectar
   flujos nuevos — se salta con aviso si ese archivo no existe, sin
   detener el resto del pipeline.
6. **Genera el Excel final** con todo consolidado, y borra los CSV/TXT
   intermedios (ya quedaron embebidos en el Excel).

Si algo fue mal en el paso 1 (tabla no existe, credenciales inválidas,
etc.) el pipeline se detiene ahí con un mensaje claro. Si `events-manager`
falla, **no detiene nada** — solo la columna Transmisiones queda vacía.

---

## 6. Estructura de carpetas que genera

```
flujosscript/
├── descargas/                          <- JSON crudos descargados de Dynamo
│   ├── config-control/<ambiente>/<fecha>/
│   │   ├── R2/, R3/ms/, R3/topics/, R3_Nuevos/
│   │   └── manifest.json               <- quien/cuando/cuantos items
│   ├── text-analyzer/<ambiente>/<fecha>/
│   │   └── use_case/, use_case_TA/
│   └── events-manager/<ambiente>/<fecha>/
│       └── crudos/, resultados/
│
├── reportes/<ambiente>/<fecha>/
│   └── reporte_completo.xlsx           <- EL ENTREGABLE para el usuario final
│
└── referencias/                        <- configuracion editable (ver seccion 7)
```

Las fechas son formato `YYYY-MM-DD` (ordenan bien alfabéticamente). En
`reportes/`, si corres el pipeline más de una vez el mismo día, la corrida
más reciente reemplaza a la anterior.

`descargas/` y `reportes/` están en `.gitignore` — son datos generados,
no se suben al repositorio.

---

## 7. Archivos de configuración (`referencias/`)

| Archivo | Para qué sirve |
|---|---|
| `pipeline_config.json` | Observaciones manuales (por qué un flujo no tiene match con TA) y el orden por defecto del Reporte Agrupado |
| `fuente_orden_reporte.json` | Conexión **opcional** a un Excel maestro (SharePoint/OneDrive) para que el orden del reporte venga de ahí en vez de la lista fija. Desactivado por defecto (`"activo": false`) |
| `Orden_RE_Base.txt` | **Falta crear este archivo.** Lista (una por línea) de nombres de JSON R3 ya catalogados, usada por el paso 5/6 (`validar-nuevos`) para detectar flujos nuevos |

### Activar la fuente del Excel maestro (`fuente_orden_reporte.json`)

```json
{
  "activo": true,
  "ruta_archivo": "C:/Users/tu.usuario/OneDrive - Banco/Ruta/Maestro.xlsx",
  "hoja": "Orden",
  "columna": "Nombre del Flujo",
  "fila_encabezado": 1
}
```

Funciona leyendo directamente el archivo local (la carpeta de SharePoint
sincronizada con OneDrive se ve como una carpeta normal de Windows — no
hace falta ninguna API ni login). Si la ruta/hoja/columna están mal, o el
archivo no existe en esa máquina, el pipeline **no se cae**: usa la lista
estática de `pipeline_config.json` y deja un aviso en el log.

---

## 8. Credenciales AWS

Tres formas, de más a menos cómoda:

1. **Archivo de credenciales** (recomendado): `aws_credentials.json` en la
   raíz del proyecto (o cualquier ruta, pasada con `--credenciales-file`).
   El menú lo detecta solo si tiene ese nombre exacto.
   ```json
   {
     "aws_access_key_id": "AKIA...",
     "aws_secret_access_key": "...",
     "aws_session_token": "..."   // opcional, solo si son credenciales temporales
   }
   ```
   **Nunca subas este archivo a git** — ya está bloqueado en `.gitignore`.

2. **Perfil de AWS** (`--perfil nombre-del-perfil`): usa lo que tengas
   configurado con `aws configure` o `aws sso login`.

3. **Variables de entorno**: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
   `AWS_SESSION_TOKEN` — el comportamiento clásico, sigue funcionando.

---

## 9. El Excel final (`reporte_completo.xlsx`)

Hojas, en este orden:

1. **Resumen** — ambiente, fecha (en español, ej. "15 de septiembre de
   2026, 9:24 PM"), y totales clave de la corrida.
2. **Reporte Agrupado** — la hoja principal: una fila por flujo,
   subtipo/cantidad agrupados visualmente (celdas combinadas), bandas de
   color alternas, columna Transmisiones en verde cuando aplica, y
   observaciones con "ALERTA" resaltadas en rojo.
3. **Comparacion - Clasificados / Revisar** — qué R3 sí y no tienen match
   con Text Analyzer.
4. **Subtipos Repetidos** — solo aparece si hay alguno.
5. **Nuevos vs Baseline** — solo aparece si existe `Orden_RE_Base.txt`.

Paleta de colores: encabezado amarillo `#FDDA24` con texto negro en
negrita, bordes gris oscuro `#9C9A98`, banda alterna gris muy sutil
`#FAFAF9`.

---

## 10. Tests

```powershell
pip install -r requirements-dev.txt
pytest -v
```

62 tests cubren toda la lógica (clasificación de descargas, comparación,
subtipos repetidos, reporte agrupado, nuevos vs baseline, identificación
de eventos UDZ, credenciales, fuente del Excel maestro) sin necesitar AWS.

---

## 11. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'boto3'` | Faltan dependencias, o estás usando otro Python | `pip install -r requirements.txt` (verifica que sea el mismo `python` que corre el pipeline) |
| `Las credenciales de AWS expiraron o son invalidas` | El token temporal caducó (normalmente 1 hora) | Consigue credenciales nuevas y actualiza `aws_credentials.json` |
| `La tabla '...' no existe en esta cuenta/region` | Ambiente equivocado, o esa tabla no existe ahí | Revisa que `qa`/`pdn`/`dev` sea el correcto |
| Paso 5/6 se salta con aviso | No existe `referencias/Orden_RE_Base.txt` | Es opcional; créalo cuando tengas el catálogo base |
| Columna "Transmisiones" vacía | Falló la descarga de `events-manager` (tabla no existe en ese ambiente, sin permisos, etc.) | Revisa el `WARNING` en el log; no detiene el resto del pipeline |
| Traceback con números de línea que no cuadran con el código | Caché de Python desactualizado (`__pycache__`) | Bórralo: `find . -name __pycache__ -exec rm -rf {} +` (o simplemente ignóralo, Python lo regenera solo) |

---

## 12. Estructura del código (`python_pipeline/`)

| Módulo | Responsabilidad |
|---|---|
| `cli.py` | Punto de entrada, subcomandos, orquestación del pipeline completo |
| `menu.py` | Menú interactivo |
| `config.py` | Tablas soportadas, rutas, carga de `pipeline_config.json` |
| `common.py` | Utilidades compartidas (parseo JSON, normalización de texto, fechas legibles) |
| `aws_client.py` | Sesión y validación de credenciales AWS |
| `download.py` | Scan de DynamoDB, clasificación y guardado en `descargas/` |
| `compare.py` | Paso 2: R3 vs Text Analyzer |
| `verify_repeated.py` | Paso 3: subtipos repetidos |
| `group_report.py` | Paso 4: reporte agrupado |
| `new_vs_baseline.py` | Paso 5: nuevos vs `Orden_RE_Base.txt` |
| `events_analysis.py` | Identificación crudos/transmisiones en events-manager |
| `excel_report.py` | Construcción del `.xlsx` final |
| `sharepoint_source.py` | Lectura opcional del orden desde un Excel maestro local |
