# Cruce de IDs de transmisiones R2

El script `cruce_inventario_ids.py` cruza el archivo `INVENTARIO_r2_general.csv` (Este fue un export de la pestaña de solo R2) con los Excel `Inventario_ids_S3RAW.xlsx` e `Inventario_ids_S3RESULTS.xlsx` ESTOS DOS ARCHIVOS se obtuvieron desde GoA.

Actualiza en el CSV las columnas:

- `ID TXS (RAW)`: toma el ID desde la columna C del Excel RAW cuando `s3_path` coincide con `Ruta Destino`.
- `ID TXS (RESULTS)`: toma el ID desde la columna C del Excel RESULTS cuando `s3_path` coincide con `Ruta Origen`.

Si no encuentra coincidencia, escribe `N/A`.

## Normalizacion aplicada

Para comparar rutas, el script normaliza:

- Prefijos `s3://bucket/`.
- Barras `/` y `\`.
- Prefijo inicial `AID` o `/AID/`.
- Barras repetidas.
- Barra final.
- Diferencias entre mayusculas y minusculas.

## Archivos generados

- `INVENTARIO_r2_transmisiones.csv`: inventario actualizado con IDs RAW y RESULTS.
- `IDS_RAW_NO_USADOS.csv`: registros del Excel RAW que no hicieron match con el CSV, con campos adicionales.
- `IDS_RESULTS_NO_USADOS.csv`: registros del Excel RESULTS que no hicieron match con el CSV, con campos adicionales.

## Ejecucion

Desde esta carpeta:

```bash
python cruce_inventario_ids.py
```

El script imprime trazabilidad con total de registros procesados, coincidencias RAW, coincidencias RESULTS y registros sin coincidencia.

# Cruce de IDs de transmisiones R3

El script `cruce_inventario_ids_r3.py` cruza el CSV `reporte_documentos_encontrados_aid(Inventario R3).csv` (Este se exporta desde el excel reporte que tenemos en sharepoint, se exporta como CSV) con el Excel `Inventario_udz.xlsx` (pestaña `Detalle_Schedules`), recordar  que este excel sale de GoA .

Actualiza en el CSV las columnas:

- `ID TXS (CRUDOS)`: toma el ID cuando `s3_path` (sin bucket) coincide con `Ruta Destino`.
- `ID TXS (TRANS)`: toma la misma ruta, reemplaza el segmento inicial `/crudos/` por `/transmisiones/`, y busca coincidencia en `Ruta Origen`.

Si no encuentra coincidencia, escribe `N/A`. La normalizacion de rutas es la misma que en el cruce R2.

## Archivos generados

- `INVENTARIO_transmisiones_r3.csv`: inventario actualizado con IDs CRUDOS y TRANS.
- `IDS_RAW_NO_USADOS_r3.csv`: registros del Excel que no hicieron match ni como CRUDOS ni como TRANS.

## Ejecucion

Desde esta carpeta:

```bash
python cruce_inventario_ids_r3.py
```