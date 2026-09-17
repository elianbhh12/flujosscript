# Pipeline Dynamo — config-control / text-analyzer / events-manager (UDZ)

Herramienta para descargar, comparar y auditar la configuración de flujos de
procesamiento de documentos que vive en DynamoDB, y entregar **Excels
únicos y presentables** con el inventario actualizado de cada ambiente.

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
- ¿Qué flujos son **nuevos**, **cambiaron** o **desaparecieron** desde la última corrida?
- ¿Qué hay en **PDN que todavía no está en QA**?
- ¿Qué tenemos, en total, en cada ambiente — sin importar cuándo se descargó cada cosa?

Todo esto se entrega en **archivos Excel**, listos para revisar sin abrir CSVs sueltos.

---

## 2. Requisitos

- **Python 3.9 o superior**
- Paquetes: `boto3` (acceso a AWS/DynamoDB) y `openpyxl` (generar los Excel)
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

Te muestra un menú (ver sección 4 más abajo) y te va preguntando lo
necesario en cada paso (ambiente, modo de descarga, credenciales, rutas
— con valores por defecto sugeridos automáticamente).

### Opción C — Comandos directos (para automatizar / expertos)

```powershell
# Pipeline completo (descarga + análisis + Excel), sin preguntas:
python -m python_pipeline.cli run-all --env qa --credenciales-file aws_credentials.json

# Igual, pero forzando descarga completa (no incremental):
python -m python_pipeline.cli run-all --env qa --modo-descarga completo --credenciales-file aws_credentials.json

# Solo descargar una tabla:
python -m python_pipeline.cli descargar --env qa --tabla text-analyzer --dry-run

# Pasos individuales (para reprocesar sin volver a descargar):
python -m python_pipeline.cli comparar --r3-dir X --ta-dir Y --out-dir Z
python -m python_pipeline.cli verificar --r3-dir X --out-txt salida.txt
python -m python_pipeline.cli agrupar --r3-dir X --detalle-csv D --out-csv salida.csv
python -m python_pipeline.cli validar-nuevos --r3-dir X --out-csv salida.csv
python -m python_pipeline.cli identificar-eventos --events-dir X --out-xlsx salida.xlsx
```

Cada subcomando tiene ayuda propia: `python -m python_pipeline.cli <comando> --help`.

### Instalarlo como comando corto (opcional)

```powershell
pip install -e .
aid-pipeline          # equivalente a "python -m python_pipeline.cli"
```

---

## 4. El menú interactivo, explicado a fondo

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

Cada opción llama, por dentro, a un módulo de `python_pipeline/` — el
menú solo hace las preguntas y arma los parámetros. Las opciones **3-7
autodetectan la última descarga** de cada tabla y la sugieren como valor
por defecto (basta con presionar Enter si es la que quieres).

### 1) Descargar una tabla

**Qué hace**: descarga el contenido de una tabla DynamoDB (`config-control`,
`text-analyzer`, `events-manager`, o varias a la vez) y la guarda como
archivos JSON locales, clasificados en carpetas.

**Cómo lo hace**:
1. Te pregunta ambiente, tabla, y **modo de descarga**:
   - **`incremental`** (default, rápido): compara contra la última
     descarga de esa tabla/ambiente (la detecta sola, buscando la carpeta
     de fecha más reciente en `descargas/`) y **solo trae lo que no
     conocía**. Lo que ya existía no se vuelve a bajar ni a escribir.
   - **`completo`** (más lento): ignora cualquier descarga anterior y trae
     **todo** lo que hay hoy en la tabla.
2. Valida tus credenciales AWS (`sts get-caller-identity`).
3. Escanea la tabla con `boto3` en paralelo (el número de "segmentos" se
   calcula solo según cuántos items tiene la tabla — no hay que
   configurarlo a mano).
4. Cada item se clasifica según su `s3_path`:
   - `r2-raw`/`s3-raw` en la ruta → carpeta `R2`
   - `udz` en la ruta, con algún paso `TYPE: "topic"` → `R3/topics`
   - `udz` en la ruta, sin pasos `topic` → `R3/ms`
   - Ninguno de los anteriores → `R3_Nuevos` (para revisión manual)
   - Para `events-manager`: `crudos/` o `resultados/` según la ruta
5. Si dos items terminan compartiendo el mismo nombre de archivo, el
   segundo se renombra usando su ruta completa (para no pisar al primero)
   y ambos quedan registrados como "nombres repetidos".
6. Guarda un `manifest.json` por descarga con quién/cuándo/cuántos items.

**Resultado**: `descargas/<tabla>/<ambiente>/<fecha>/` con los JSON, más
`manifest.json`. Esta opción **no genera ningún Excel** — es solo la
descarga. Para ver resultados en Excel, sigue con la opción 3, 5, o usa
la 2 directamente.

### 2) Ejecutar pipeline completo — la opción que usas normalmente

**Qué hace**: encadena los 7 pasos completos (descarga → comparar →
verificar → agrupar → actualizar maestro/historial → validar catálogo →
generar Excel) para un ambiente, y te deja **3 archivos Excel** listos
para abrir (los abre automáticamente al terminar).

**Cómo lo hace**, paso a paso:

| Paso | Qué hace | Detalle |
|---|---|---|
| 1/7 | Descarga `config-control`, `text-analyzer` y `events-manager` | En el modo que elegiste (incremental/completo). Si `events-manager` falla, no detiene nada — solo la columna Transmisiones queda vacía |
| 2/7 | Compara R3 vs Text Analyzer | Cruza `use_case` (de cada JSON R3) contra `cu_name` (de Text Analyzer). Si no hay match, marca "SIN_USE_CASE" |
| 3/7 | Busca subtipos repetidos | Agrupa por `tipoDocumento` normalizado (sin tildes/mayúsculas); si más de un archivo comparte el mismo subtipo, lo reporta |
| 4/7 | Agrupa el reporte por subtipo | Arma una fila por flujo con subtipo, TA, proceso, transmisiones y tipo (R3-Topics/R3-MS), agrupado visualmente |
| 5/7 | Actualiza el maestro global del ambiente | Ver sección 5 — mezcla lo descargado hoy con lo que ya se sabía; en modo completo también detecta eliminados |
| 6/7 | Compara contra el catálogo (`Orden_RE_Base.txt`) | Si ese archivo no existe, se salta con aviso — el resto sigue igual |
| 7/7 | Genera el Excel final | Arma `reporte_completo.xlsx`, y actualiza `maestro_<ambiente>.xlsx`, `historial_<ambiente>.xlsx` y `matriz_ambientes.xlsx` |

Si algo falla en el paso 1 (tabla no existe, credenciales inválidas,
problema de red/certificado), el pipeline se detiene ahí con un mensaje
claro. Todo lo demás (pasos 2 en adelante) solo corre si hubo datos R3
y Text Analyzer descargados.

### 3) Comparar R3 vs Text Analyzer

**Qué hace**: repite solo el paso 2 del pipeline completo, sin volver a
descargar nada — útil para reprocesar una descarga que ya tienes en disco.

**Cómo lo hace**: por cada JSON en la carpeta R3 que le indiques, busca
dentro del archivo (recursivamente) un campo `STEP_VARIABLES.use_case`, y
lo compara contra el `cu_name` de cada JSON de Text Analyzer. Si dos o
más flujos R3 comparten el mismo `use_case`, lo marca ("Comparte TA").
Si un flujo no tiene `use_case` o no hace match, cae en "no clasificados"
con una observación (algunas ya conocidas de antemano, en
`referencias/pipeline_config.json`).

**Resultado**: 3 archivos en la carpeta de salida que le des —
`clasificados/ta_cu_name.txt`, `no_clasificados/r3_sin_ta.txt`,
`detalle_r3_vs_ta.csv` (este último lo necesita la opción 5).

### 4) Verificar subtipos repetidos

**Qué hace**: repite el paso 3, de forma aislada.

**Cómo lo hace**: lee cada JSON R3, extrae `workflow_variables.tipoDocumento`
(o lo busca en cualquier parte del archivo si no está ahí), lo normaliza
(minúsculas, sin tildes/símbolos) y agrupa. Cualquier grupo con más de un
archivo se reporta, listando también el `proceso` de cada uno.

**Resultado**: un `.txt` con el detalle de cada subtipo repetido y sus
archivos/procesos.

### 5) Agrupar reporte por subtipos

**Qué hace**: repite el paso 4 — arma el reporte agrupado a partir de una
carpeta R3 y un `detalle_r3_vs_ta.csv` que ya tengas (de la opción 3).

**Cómo lo hace**: agrupa los flujos por subtipo (normalizado) y los ordena
según `referencias/pipeline_config.json` (o el Excel maestro de SharePoint,
si lo activaste — ver sección 7). Los flujos que no están en esa lista se
agregan al final, ordenados alfabéticamente. Los que sí comparten subtipo
quedan **siempre contiguos** (aunque no estén en la lista de orden), para
que la celda combinada del Excel no mezcle subtipos de flujos distintos.

**Resultado**: un `.csv` con una fila por flujo, subtipo/cantidad solo en
la primera fila de cada grupo, y columna `Tipo` (R3-Topics/R3-MS) al final.

### 6) Validar nuevos R3 vs Orden_RE_Base.txt

**Qué hace**: compara los flujos de una carpeta R3 contra el catálogo base
(`referencias/Orden_RE_Base.txt`) y lista los que **no están ahí** — es
decir, flujos nuevos que todavía no se agregaron al catálogo oficial.

**Cómo lo hace**: `Orden_RE_Base.txt` es una lista de nombres de archivo,
uno por línea. Cualquier JSON R3 cuyo nombre no aparezca en esa lista se
reporta como nuevo, con las mismas columnas que el reporte maestro
histórico (para poder copiar/pegar directamente ahí).

**Requiere** que `referencias/Orden_RE_Base.txt` exista — si no, avisa y
no hace nada (en el pipeline completo, este paso simplemente se salta).

### 7) Identificar eventos UDZ (crudos / transmisiones)

**Qué hace**: para una carpeta de `events-manager` ya descargada, dice
por cada flujo si tiene **solo crudos**, **crudos + transmisiones**, o
(anómalo) **solo transmisiones sin crudos**.

**Cómo lo hace**: agrupa los archivos por la parte del `s3_path` que
queda igual entre `crudos/` y `resultados/` (todo después de esa palabra).
Un flujo con datos en ambas carpetas = "Crudos + Transmisiones"; solo en
`crudos/` = "Solo Crudos"; solo en `resultados/` = alerta, porque crudos
debería existir siempre.

**Resultado**: un Excel con una fila por flujo y las alertas resaltadas
en rojo.

---

## 5. Los 3 archivos "globales" (fuera de cualquier corrida puntual)

Además del `reporte_completo.xlsx` de cada corrida (que vive en
`reportes/<ambiente>/<fecha>/`), el pipeline completo mantiene **3
archivos acumulados por ambiente**, en la raíz de `reportes/`, que se
van actualizando corrida tras corrida (no se pisan con la fecha):

| Archivo | Qué es | Se actualiza |
|---|---|---|
| **`maestro_<ambiente>.xlsx`** | El estado **completo** conocido de ese ambiente — mismas columnas que Reporte Agrupado, pero acumulado, sin importar qué tan chica haya sido la descarga de hoy | Siempre |
| **`historial_<ambiente>.xlsx`** | Log de cada NUEVO / CAMBIO / ELIMINADO detectado, con fecha | Siempre (solo agrega filas, nunca borra) |
| **`matriz_ambientes.xlsx`** | Por cada flujo: ¿está en QA? ¿en PDN? ¿en DEV? Con alerta si está en PDN pero no en QA | Siempre, para cualquier ambiente que corras |

### Por qué existen (y por qué importa el modo de descarga)

El punto clave: **el maestro nunca se pisa**. Si hoy descargas en modo
`incremental` y solo hay 1 flujo nuevo, el maestro sigue mostrando los
230 que ya conocía de antes — no los pierde por no haberlos vuelto a
descargar.

La diferencia entre modos solo afecta si se pueden detectar **eliminados**:
- En modo `incremental`, si un flujo no aparece en la descarga de hoy, el
  pipeline **no sabe** si sigue existiendo en Dynamo (simplemente no se
  volvió a pedir) o si de verdad lo borraron — así que nunca lo marca
  como eliminado.
- En modo `completo`, como se trae *todo*, cualquier flujo que estaba
  presente y hoy no aparece en la tabla **sí se marca como eliminado**
  de verdad.

**Recomendación**: corre `incremental` en el día a día (rápido), y de vez
en cuando (semanal, por ejemplo) corre `completo` para que el maestro
pueda confirmar eliminados reales.

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
├── reportes/
│   ├── <ambiente>/<fecha>/
│   │   └── reporte_completo.xlsx       <- reporte de ESA corrida
│   ├── maestro_<ambiente>.xlsx         <- acumulado, global (seccion 5)
│   ├── historial_<ambiente>.xlsx       <- log de cambios, global
│   └── matriz_ambientes.xlsx           <- qa/pdn/dev cruzados, global
│
├── historial/                          <- estado interno (NO son reportes,
│   └── <ambiente>/                        no los abras a mano; son JSON
│       ├── estado_actual.json             que el programa usa para saber
│       └── eventos.json                   que sabia la ultima vez)
│
└── referencias/                        <- configuracion editable (ver seccion 7)
```

Las fechas son formato `YYYY-MM-DD` (ordenan bien alfabéticamente). En
`reportes/<ambiente>/<fecha>/`, si corres el pipeline más de una vez el
mismo día, la corrida más reciente reemplaza a la anterior — pero
`maestro_<ambiente>.xlsx`, `historial_<ambiente>.xlsx` y
`matriz_ambientes.xlsx` **nunca se pisan**, se van acumulando.

`descargas/`, `reportes/` y `historial/` están en `.gitignore` — son
datos generados, no se suben al repositorio. **Importante**: nunca borres
`historial/` a mano — si lo borras, el pipeline pierde la memoria de qué
ya conocía y la próxima corrida marca todo como "nuevo" otra vez.

---

## 7. Archivos de configuración (`referencias/`)

| Archivo | Para qué sirve |
|---|---|
| `pipeline_config.json` | Observaciones manuales (por qué un flujo no tiene match con TA) y el orden por defecto del Reporte Agrupado |
| `fuente_orden_reporte.json` | Conexión **opcional** a un Excel maestro (SharePoint/OneDrive) para que el orden del reporte venga de ahí en vez de la lista fija. Desactivado por defecto (`"activo": false`) |
| `Orden_RE_Base.txt` | **Falta crear este archivo.** Lista (una por línea) de nombres de JSON R3 ya catalogados, usada por el paso 6 (`validar-nuevos`) para detectar flujos nuevos |

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

**Verificación TLS**: en la red del banco, un proxy/firewall reemplaza el
certificado al conectar a AWS. Por eso las conexiones usan `verify=False`
por defecto (`aws_client.VERIFY_TLS`) — si algún día el banco instala su
CA corporativa en el almacén de certificados de Python, se puede volver a
activar la verificación cambiando esa única constante.

---

## 9. Los Excel que genera (hojas y colores)

### `reporte_completo.xlsx` (por corrida)

1. **Resumen** — ambiente, fecha (en español), y totales clave.
2. **Reporte Agrupado** — la hoja principal: subtipo/cantidad agrupados
   visualmente (celdas combinadas), columna Transmisiones en verde,
   columna Tipo (R3-Topics/R3-MS), observaciones "ALERTA" en rojo.
3. **Historial (vs corrida anterior)** — solo si hubo cambios.
4. **Nombres Repetidos** — solo si `download.py` detectó colisiones.
5. **R2 (raw)** — solo si hubo items clasificados como R2.
6. **Comparacion - Clasificados / Revisar** — match/no-match con Text Analyzer.
7. **Subtipos Repetidos** — solo si hay alguno.
8. **Nuevos vs Baseline** — solo si existe `Orden_RE_Base.txt`.

### `maestro_<ambiente>.xlsx` / `matriz_ambientes.xlsx` / `historial_<ambiente>.xlsx`

Ver sección 5.

### Paleta de colores (en todas las hojas)

Encabezado amarillo `#FDDA24` con texto negro en negrita, bordes gris
oscuro `#9C9A98`, banda alterna gris muy sutil `#FAFAF9`.

---

## 10. Tests

```powershell
pip install -r requirements-dev.txt
pytest -v
```

82 tests cubren toda la lógica (clasificación de descargas en modo
incremental/completo, comparación, subtipos repetidos, reporte agrupado,
maestro/historial por ambiente, matriz de ambientes, nuevos vs baseline,
identificación de eventos UDZ, credenciales, fuente del Excel maestro)
sin necesitar AWS.

---

## 11. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'boto3'` | Faltan dependencias, o estás usando otro Python | `pip install -r requirements.txt` (verifica que sea el mismo `python` que corre el pipeline) |
| `Las credenciales de AWS expiraron o son invalidas` | El token temporal caducó (normalmente 1 hora) | Consigue credenciales nuevas y actualiza `aws_credentials.json` |
| `No se pudo conectar a AWS (¿estas en la red del banco?)` | Problema de red/certificado, o no estás en la VPN/red correcta | Revisa tu conexión; el `verify=False` ya está activado por defecto |
| `La tabla '...' no existe en esta cuenta/region` | Ambiente equivocado, o esa tabla no existe ahí | Revisa que `qa`/`pdn`/`dev` sea el correcto |
| Paso 6/7 se salta con aviso | No existe `referencias/Orden_RE_Base.txt` | Es opcional; créalo cuando tengas el catálogo base |
| Columna "Transmisiones" vacía | Falló la descarga de `events-manager` (tabla no existe en ese ambiente, sin permisos, etc.) | Revisa el `WARNING` en el log; no detiene el resto del pipeline |
| El maestro marca "eliminados" que en realidad siguen existiendo | Se usó modo `incremental` pero algo confundió al pipeline | No debería pasar (el modo incremental nunca marca eliminados); si pasa, revisa que `--modo-descarga` sea el correcto |
| Traceback con números de línea que no cuadran con el código | Caché de Python desactualizado (`__pycache__`) | Bórralo: `find . -name __pycache__ -exec rm -rf {} +` (o simplemente ignóralo, Python lo regenera solo) |

---

## 12. Estructura del código (`python_pipeline/`)

| Módulo | Responsabilidad |
|---|---|
| `cli.py` | Punto de entrada, subcomandos, orquestación del pipeline completo |
| `menu.py` | Menú interactivo |
| `config.py` | Tablas soportadas, rutas, carga de `pipeline_config.json` |
| `common.py` | Utilidades compartidas (parseo JSON, normalización de texto, fechas legibles) |
| `aws_client.py` | Sesión, credenciales, y verificación TLS de AWS |
| `download.py` | Scan de DynamoDB (incremental o completo), clasificación y guardado en `descargas/` |
| `compare.py` | Paso 2: R3 vs Text Analyzer |
| `verify_repeated.py` | Paso 3: subtipos repetidos |
| `group_report.py` | Paso 4: reporte agrupado (y helpers reusados por el maestro) |
| `historial.py` | Maestro acumulado por ambiente + log de nuevo/cambio/eliminado |
| `matriz_ambientes.py` | Presencia de cada flujo en qa/pdn/dev |
| `new_vs_baseline.py` | Paso 6: nuevos vs `Orden_RE_Base.txt` |
| `events_analysis.py` | Identificación crudos/transmisiones en events-manager |
| `excel_report.py` | Construcción de todos los `.xlsx` |
| `sharepoint_source.py` | Lectura opcional del orden desde un Excel maestro local |
