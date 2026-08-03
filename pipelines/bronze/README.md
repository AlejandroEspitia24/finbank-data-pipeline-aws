# Capa Bronze — Ingesta cruda

## Qué hace

Copia las 6 tablas del sistema origen (RDS PostgreSQL) hacia S3 en formato
Parquet, con el mínimo de transformaciones: mismo esquema, mismos tipos,
mismos nombres de columna. Bronze es la única fuente de verdad del dato
original — cualquier estado anterior del pipeline debe poder reproducirse
desde aquí.

## Decisiones de diseño

**Modo incremental sin columna `updated_at`.** El esquema origen (Fase 1) no
incluye una columna técnica de auditoría de última modificación. Supuesto
documentado: se usa el campo de fecha de negocio más relevante de cada tabla
de hechos como marca de agua (`fec_mov`, `fec_desembolso`, `fec_cobro`),
válido porque el dataset sintético es solo de inserciones, sin updates
posteriores a registros existentes. Las tablas pequeñas tipo dimensión
(`tb_clientes_core`, `tb_productos_cat`, `tb_sucursales_red`) se recargan
completas en cada ejecución — a su volumen, es más simple y no más costoso
que mantener lógica incremental.

**Estado del watermark:** JSON de control en
`s3://<bronze-bucket>/_control/watermarks/<tabla>.json`. Sin base de datos
externa — todo el estado del pipeline vive dentro del propio Data Lake.

**Particionamiento:** por fecha de **ingesta** (año/mes/día), no por fecha de
negocio — es lo que exige el enunciado explícitamente, y es lo que permite
consultas incrementales eficientes sobre "qué llegó hoy" sin tener que leer
particiones históricas completas.

**Idempotencia:** `spark.sql.sources.partitionOverwriteMode = dynamic` +
`mode("overwrite")`. Al reescribir, Spark solo reemplaza las particiones
(año/mes/día) presentes en el DataFrame que se está escribiendo — nunca
borra ni duplica datos de ejecuciones anteriores en otras fechas. Correr el
job dos veces el mismo día sobre los mismos datos no genera duplicados.

**Manejo de errores:** cada tabla se procesa dentro de su propio
`try/except`. Si una tabla falla, se registra en el log de ejecución con
`status=FAILED` y el pipeline continúa con las tablas restantes — una tabla
rota no debe tumbar la ingesta completa.

**Log de ejecución:** un registro JSON por tabla en
`s3://<bronze-bucket>/_control/ingestion_log/`, con registros procesados,
tamaño del archivo generado y duración — tal como exige el enunciado.

## Argumentos del job

| Argumento | Descripción |
|---|---|
| `--rds_connection_name` | Nombre de la conexión Glue JDBC creada en la Fase 2 |
| `--bronze_bucket` | Nombre del bucket S3 de la capa Bronze |
| `--extra-py-files` | Ruta S3 de `pipelines/common/glue_utils.py` |

Ninguna credencial se pasa como argumento: `glue_context.extract_jdbc_conf()`
resuelve usuario/password directamente desde la conexión Glue (que a su vez
los lee de Secrets Manager), sin que el script los reciba ni los escriba.
