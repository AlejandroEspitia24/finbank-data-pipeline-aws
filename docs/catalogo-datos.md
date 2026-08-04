# Catálogo de Datos — Capas Silver y Gold

Catálogo de datos básico en Markdown (Fase 5, exigido por el enunciado):
cada tabla de las capas Silver y Gold, con la descripción de **cada
campo**, su tipo, su origen y si contiene información sensible (PII). No
reemplaza al Glue Data Catalog (creado en la Fase 2, poblado por los
Crawlers) — ese ya expone tipos y particiones automáticamente. Lo que este
documento agrega es el contexto que un catálogo técnico automático no
captura: qué columna es PII, por qué existe una columna calculada, y de
qué tabla origen viene cada cosa.

Convención de sensibilidad:
- 🔴 **PII directa** — identifica a una persona sin ambigüedad.
- 🟡 **PII indirecta / cuasi-identificador** — combinada con otras columnas puede reidentificar, o es información sensible de negocio (crediticia, de comportamiento) atada a una persona.
- 🟢 **No sensible** — dato operativo o agregado sin riesgo de reidentificación.

Ubicación física: `s3://finbank-{silver|gold}-dev-<account_id>/<tabla>/`, formato Parquet.

---

## Capa Silver

### `tb_clientes_core`
Origen: RDS `tb_clientes_core` (vía Bronze).

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `id_cli` | bigint | RDS (PK) | 🟢 |
| `nomb_cli` | string | RDS | 🔴 (nombre de pila) |
| `apell_cli` | string | RDS | 🔴 (apellido) |
| `tip_doc` | string | RDS | 🟢 |
| `num_doc_hash` | string (SHA-256) | Calculado en Silver desde `num_doc` (original eliminado) | 🟡 (PII hasheada, irreversible) |
| `fec_nac` | date | RDS | 🟡 (permite calcular edad exacta) |
| `fec_alta` | date | RDS | 🟢 |
| `cod_segmento` | string | RDS | 🟢 |
| `score_buro` | int | RDS (imputado con mediana si nulo) | 🟡 (dato crediticio) |
| `score_buro_imputado` | boolean | Calculado en Silver | 🟢 |
| `ciudad_res` | string | RDS | 🟡 (cuasi-identificador combinado con edad/nombre) |
| `depto_res` | string | RDS (imputado con `"SIN_INFORMAR"` si nulo) | 🟡 |
| `estado_cli` | string | RDS | 🟢 |
| `canal_adquis` | string | RDS (imputado con `"DESCONOCIDO"` si nulo) | 🟢 |

### `tb_productos_cat`
Origen: RDS `tb_productos_cat` (vía Bronze). Sin transformaciones de Silver más allá de trim/dedupe.

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `cod_prod` | string | RDS (PK) | 🟢 |
| `desc_prod` | string | RDS | 🟢 |
| `tip_prod` | string | RDS | 🟢 |
| `tasa_ea` | decimal | RDS | 🟢 |
| `plazo_max_meses` | int | RDS | 🟢 |
| `cuota_min` | decimal | RDS | 🟢 |
| `comision_admin` | decimal | RDS | 🟢 |
| `estado_prod` | string | RDS | 🟢 |

### `tb_sucursales_red`
Origen: RDS `tb_sucursales_red` (vía Bronze). Sin transformaciones de Silver más allá de trim/dedupe.

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `cod_suc` | string | RDS (PK) | 🟢 |
| `nom_suc` | string | RDS | 🟢 |
| `tip_punto` | string | RDS | 🟢 |
| `ciudad` | string | RDS | 🟢 |
| `depto` | string | RDS | 🟢 |
| `latitud` | decimal | RDS | 🟢 |
| `longitud` | decimal | RDS | 🟢 |
| `activo` | boolean | RDS | 🟢 |

### `tb_mov_financieros`
Origen: RDS `tb_mov_financieros` (vía Bronze).

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `id_mov` | bigint | RDS (dedupe por duplicados exactos) | 🟢 |
| `id_cli` | bigint | RDS (FK validada contra `tb_clientes_core`) | 🟡 (liga el movimiento a una persona) |
| `cod_prod` | string | RDS (FK validada) | 🟢 |
| `num_cuenta_hash` | string (SHA-256) | Calculado en Silver desde `num_cuenta` (original eliminado) | 🟡 (PII hasheada) |
| `fec_mov` | date | RDS (validado contra rango de fechas esperado) | 🟢 |
| `hra_mov` | time | RDS | 🟢 |
| `vr_mov` | decimal | RDS | 🟡 (monto de transacción, comportamiento financiero) |
| `tip_mov` | string | RDS | 🟢 |
| `cod_canal` | string | RDS (imputado con `"DESCONOCIDO"` si nulo) | 🟢 |
| `cod_canal_imputado` | boolean | Calculado en Silver | 🟢 |
| `cod_ciudad` | string | RDS | 🟢 |
| `cod_estado_mov` | string | RDS | 🟢 |
| `id_dispositivo` | string | RDS (imputado con `"NO_DISPONIBLE"` si nulo) | 🟡 (identificador de dispositivo, cuasi-PII) |
| `id_dispositivo_imputado` | boolean | Calculado en Silver | 🟢 |
| `ind_sospechoso` | boolean | Calculado en Silver (ventana de 30 días por cliente, `vr_mov > promedio + 3·desv.est.`) | 🟡 (señal de fraude, sensible operativamente) |

### `tb_obligaciones`
Origen: RDS `tb_obligaciones` (vía Bronze).

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `id_oblig` | bigint | RDS (PK) | 🟢 |
| `id_cli` | bigint | RDS (FK validada) | 🟡 |
| `cod_prod` | string | RDS (FK validada) | 🟢 |
| `vr_aprobado` | decimal | RDS | 🟡 (dato crediticio) |
| `vr_desembolsado` | decimal | RDS (validado `≤ vr_aprobado`) | 🟡 |
| `sdo_capital` | decimal | RDS | 🟡 |
| `vr_cuota` | decimal | RDS | 🟡 |
| `fec_desembolso` | date | RDS | 🟢 |
| `fec_venc` | date | RDS | 🟢 |
| `dias_mora_act` | int | RDS | 🟡 (comportamiento de pago) |
| `num_cuotas_pend` | int | RDS (imputado: calculado desde plazo y fechas si nulo) | 🟢 |
| `num_cuotas_pend_imputado` | boolean | Calculado en Silver | 🟢 |
| `calif_riesgo` | string | RDS | 🟡 (calificación de riesgo crediticio) |

### `tb_comisiones_log`
Origen: RDS `tb_comisiones_log` (vía Bronze).

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `id_comision` | bigint | RDS (PK) | 🟢 |
| `id_cli` | bigint | RDS (FK validada) | 🟡 |
| `cod_prod` | string | RDS (FK validada) | 🟢 |
| `fec_cobro` | date | RDS | 🟢 |
| `vr_comision` | decimal | RDS | 🟢 |
| `tip_comision` | string | RDS (imputado con `"NO_CLASIFICADA"` si nulo) | 🟢 |
| `tip_comision_imputado` | boolean | Calculado en Silver | 🟢 |
| `estado_cobro` | string | RDS | 🟢 |

### `_errors` (tabla de errores unificada)
Origen: generada por Silver, particionada por `table_name`. Contiene las mismas columnas de la tabla rechazada + `table_name`, `reason`, `batch_id`, `layer`, `timestamp`. Sensibilidad: 🟡 (contiene los mismos datos crudos de las filas rechazadas, incluyendo PII sin enmascarar de las columnas originales).

---

## Capa Gold

### `dim_clientes`
Origen: `tb_clientes_core` (Silver).

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `id_cli` | bigint | Silver (PK) | 🟢 |
| `nombre_completo` | string | Calculado: `concat(nomb_cli, apell_cli)` | 🔴 |
| `tip_doc` | string | Silver | 🟢 |
| `num_doc_hash` | string | Silver | 🟡 |
| `fec_nac` | date | Silver | 🟡 |
| `edad` | int | Calculado: `floor(datediff(hoy, fec_nac) / 365.25)` | 🟡 |
| `cod_segmento` | string | Silver | 🟢 |
| `segmento_legible` | string | Calculado: mapeo de `cod_segmento` a etiqueta legible | 🟢 |
| `score_buro` | int | Silver | 🟡 |
| `score_buro_imputado` | boolean | Silver | 🟢 |
| `ciudad_res` | string | Silver | 🟡 |
| `depto_res` | string | Silver | 🟡 |
| `estado_cli` | string | Silver | 🟢 |
| `canal_adquis` | string | Silver | 🟢 |

### `dim_productos`
Origen: `tb_productos_cat` (Silver).

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `cod_prod` | string | Silver (PK) | 🟢 |
| `desc_prod` | string | Silver | 🟢 |
| `tip_prod` | string | Silver | 🟢 |
| `familia` | string | Calculado: clasificación CREDITO/AHORRO/TRANSACCIONAL desde `tip_prod` | 🟢 |
| `tasa_ea` | decimal | Silver | 🟢 |
| `tasa_mensual_equiv` | decimal | Calculado: `(1+tasa_ea)^(1/12) - 1` | 🟢 |
| `plazo_max_meses` | int | Silver | 🟢 |
| `cuota_min` | decimal | Silver | 🟢 |
| `comision_admin` | decimal | Silver | 🟢 |
| `estado_prod` | string | Silver | 🟢 |

### `dim_geografia`
Origen: `tb_sucursales_red` (Silver), `select(ciudad, depto).distinct()`.

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `ciudad` | string | Silver | 🟢 |
| `depto` | string | Silver | 🟢 |

### `dim_canal`
Origen: `tb_sucursales_red` (Silver).

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `cod_suc` | string | Silver (PK) | 🟢 |
| `tip_punto` | string | Silver | 🟢 |
| `es_canal_digital` | boolean | Calculado: `False` para las 3 categorías físicas de `tip_punto` (ver `pipelines/gold/README.md` para el razonamiento) | 🟢 |
| `activo` | boolean | Silver | 🟢 |

### `fact_transacciones`
Origen: `tb_mov_financieros` (Silver), validado por FK contra `dim_clientes`. Particionada por `anio`/`mes`.

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `id_mov` | bigint | Silver | 🟢 |
| `id_cli` | bigint | Silver (FK contra `dim_clientes`) | 🟡 |
| `cod_prod` | string | Silver | 🟢 |
| `num_cuenta_hash` | string | Silver | 🟡 |
| `fec_mov` | date | Silver | 🟢 |
| `hra_mov` | time | Silver | 🟢 |
| `vr_mov` | decimal | Silver | 🟡 |
| `vr_mov_usd` | decimal | Calculado: `vr_mov / USD_COP_RATE` | 🟡 |
| `tip_mov` | string | Silver | 🟢 |
| `cod_canal` | string | Silver | 🟢 |
| `cod_ciudad` | string | Silver | 🟢 |
| `cod_estado_mov` | string | Silver | 🟢 |
| `flag_horario_habil` | boolean | Calculado: `hora ∈ [8,18)` | 🟢 |
| `ind_sospechoso` | boolean | Silver (propagado) | 🟡 |
| `anio`, `mes` | int (partición) | Calculado desde `fec_mov` | 🟢 |

### `fact_cartera`
Origen: `tb_obligaciones` (Silver). Particionada por `bucket_mora`.

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `id_oblig` | bigint | Silver | 🟢 |
| `id_cli` | bigint | Silver | 🟡 |
| `cod_prod` | string | Silver | 🟢 |
| `vr_aprobado` | decimal | Silver | 🟡 |
| `vr_desembolsado` | decimal | Silver | 🟡 |
| `sdo_capital` | decimal | Silver | 🟡 |
| `vr_cuota` | decimal | Silver | 🟡 |
| `fec_desembolso` | date | Silver | 🟢 |
| `fec_venc` | date | Silver | 🟢 |
| `dias_mora_act` | int | Silver | 🟡 |
| `bucket_mora` | string | Calculado: 5 rangos desde `dias_mora_act` (regla de negocio del enunciado) | 🟡 |
| `calif_riesgo` | string | Silver | 🟡 |
| `provision_pct` | decimal | Calculado: mapeo `bucket_mora → %` | 🟢 |
| `provision_estimada` | decimal | Calculado: `sdo_capital × provision_pct` | 🟡 |

### `fact_rentabilidad_cliente`
Origen: `tb_obligaciones` + `tb_productos_cat` (interés estimado) + `tb_comisiones_log` (Silver).

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `id_cli` | bigint | Silver | 🟡 |
| `periodo` | string (`yyyy-MM`) | Calculado desde `fec_desembolso`/`fec_cobro` | 🟢 |
| `ingreso_interes` | decimal | Calculado: `sdo_capital × tasa_mensual_equivalente` (supuesto documentado) | 🟡 |
| `ingreso_comisiones` | decimal | Calculado: suma de `vr_comision` con `estado_cobro = COBRADA` | 🟡 |
| `ingreso_total` | decimal | Calculado: `ingreso_interes + ingreso_comisiones` | 🟡 |
| `cltv_12m` | decimal | Calculado: suma móvil de 12 periodos de `ingreso_total` por cliente | 🟡 |

### `fact_kpis_cartera`
Origen: `fact_cartera` + `dim_clientes` (Gold), agregado — sin `id_cli` individual.

| Campo | Tipo | Origen | Sensible |
|---|---|---|---|
| `fecha` | date | Calculado: fecha de la ejecución | 🟢 |
| `cod_prod` | string | `fact_cartera` (dimensión de agregación) | 🟢 |
| `cod_segmento` | string | `dim_clientes` (dimensión de agregación) | 🟢 |
| `ciudad_res` | string | `dim_clientes` (dimensión de agregación) | 🟢 |
| `total_obligaciones_activas` | int | Calculado: `count(id_oblig)` | 🟢 |
| `monto_total_cartera` | decimal | Calculado: `sum(sdo_capital)` | 🟢 |
| `monto_en_mora` | decimal | Calculado: `sum(sdo_capital)` donde `bucket_mora ≠ AL_DIA` | 🟢 |
| `clientes_en_mora` | int | Calculado: `count_distinct(id_cli)` donde `bucket_mora ≠ AL_DIA` (agregado, sin exponer el ID) | 🟢 |
| `tasa_mora_pct` | decimal | Calculado: `monto_en_mora / monto_total_cartera × 100` | 🟢 |

---

## Cómo se controla el acceso a estos datos

Ver `infra/iam_governance.tf` (Fase 5): el rol `finbank-dev-analyst-role`
solo tiene permiso de lectura sobre el bucket **Gold** — nunca ve Silver ni
Bronze, ni por lo tanto los hashes de PII ni los datos crudos. Verificado
con `sts:AssumeRole` real contra **ambas** capas restringidas: intento de
`aws s3 ls` sobre Silver y sobre Bronze devuelven `AccessDenied` (ver
`docs/evidencia-fase5-gobernanza.md`). El rol
`finbank-dev-data-engineer-role` sí tiene acceso de lectura/escritura a
las 3 capas, consistente con su responsabilidad operativa sobre el
pipeline completo.
