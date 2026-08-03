# Capa Silver — Limpieza, conformación y calidad

## Qué hace

Lee el snapshot más reciente de cada tabla desde Bronze y produce la versión
limpia, tipada, deduplicada y sin PII expuesta que consumen los analistas y
la capa Gold. Silver es "la capa de confianza": ningún dato inconsistente
debería pasar de aquí.

## Orden de procesamiento

Dimensiones primero (`tb_productos_cat`, `tb_sucursales_red`,
`tb_clientes_core`), porque las tablas de hechos necesitan sus llaves ya
limpias para poder validar integridad referencial.

## Decisiones de diseño

**Deduplicación en dos pasos:** primero fila completa exacta (`dropDuplicates()`,
sin argumentos), que es exactamente el tipo de duplicado que la Fase 1
inyectó a propósito en `tb_mov_financieros`. Luego por llave primaria
(`dropDuplicates([pk])`), por si dos filas comparten PK pero difieren en
algún otro campo — nos quedamos con una sola versión.

**Validación de integridad referencial:** `left_semi join` contra las
dimensiones ya limpias. Los registros que no encuentran su padre se separan
a `s3://<silver-bucket>/_errors/` (particionada por tabla) con el motivo
`FK_VIOLATION_ID_INEXISTENTE`, en vez de propagarse silenciosamente.

**Reglas de negocio adicionales enviadas a la tabla de errores** (no son FK,
pero tampoco deberían llegar a Gold):
- `tb_mov_financieros`: `fec_mov` fuera de un rango histórico plausible
  (futuro, o más de ~400 días atrás) — ataca directamente la anomalía de
  fechas inyectada en la Fase 1.
- `tb_obligaciones`: `vr_desembolsado > vr_aprobado` — ataca directamente la
  anomalía de inconsistencia de negocio inyectada en la Fase 1.

**Estrategia de nulos, documentada por columna** (columnas no críticas
únicamente; las columnas críticas con nulo se descartan en
`dedupe_and_require`):

| Tabla | Columna | Estrategia |
|---|---|---|
| tb_clientes_core | depto_res | Imputación con `"SIN_INFORMAR"` |
| tb_clientes_core | canal_adquis | Imputación con `"DESCONOCIDO"` |
| tb_clientes_core | score_buro | Imputación con la mediana de la columna |
| tb_mov_financieros | id_dispositivo | Imputación con `"NO_DISPONIBLE"` |
| tb_mov_financieros | cod_canal | Imputación con `"DESCONOCIDO"` |
| tb_obligaciones | num_cuotas_pend | Cálculo derivado: `sdo_capital / vr_cuota` |
| tb_comisiones_log | tip_comision | Imputación con `"NO_CLASIFICADA"` |

Cada imputación agrega una columna indicadora binaria
(`<columna>_imputado`), para que Gold y los analistas sepan qué valores
fueron observados vs. completados — nunca se pierde esa distinción.

**Enmascaramiento de PII:** `num_doc` (clientes) y `num_cuenta`
(movimientos) se hashean con SHA-256 (irreversible) y la columna original se
elimina. Los nombres se enmascaran parcialmente (se conserva la inicial).
Esto ocurre en Silver, no antes — Bronze preserva el dato crudo intacto
porque es "la única fuente de verdad del original", como exige el
enunciado; el enmascaramiento es, por diseño, lo primero que pasa al
transformar.

**`ind_sospechoso`:** ventana de Spark particionada por `id_cli`, ordenada
por `fec_mov`, con rango `[-30 días, -1 día]` (excluye el día de la propia
transacción, para no comparar un valor contra sí mismo). Se marca sospechosa
si supera el promedio + 3 desviaciones estándar del período previo.

## 5 verificaciones automatizadas de calidad (requisito transversal del enunciado)

1. Unicidad de PK en cada una de las 6 tablas limpias
2. Cero nulos en columnas críticas (requeridas)
3. Cero registros con FK huérfana en las tablas de hechos
4. Todos los `vr_mov` de `tb_mov_financieros` son positivos
5. Todas las `fec_mov` están dentro del rango histórico plausible

Resultado escrito en `s3://<silver-bucket>/_control/dq_checks/` con estado
`PASSED`/`FAILED` por chequeo y overall.

## Salidas

| Ruta | Contenido |
|---|---|
| `s3://<silver-bucket>/<tabla>/` | Datos limpios, sin particionar |
| `s3://<silver-bucket>/_errors/table_name=<tabla>/` | Tabla de errores unificada |
| `s3://<silver-bucket>/_control/quality_report/` | Reporte de calidad por ejecución |
| `s3://<silver-bucket>/_control/dq_checks/` | Resultado de las 5 verificaciones |
