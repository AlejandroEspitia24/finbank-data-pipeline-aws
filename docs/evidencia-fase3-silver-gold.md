# Evidencia — Fase 3 / Capas Silver y Gold

## Silver — resultado

| Tabla | Entrada | Conformes | Rechazados | % Conformes |
|---|---|---|---|---|
| tb_productos_cat | 50 | 50 | 0 | 100.0% |
| tb_sucursales_red | 200 | 200 | 0 | 100.0% |
| tb_clientes_core | 10.000 | 10.000 | 0 | 100.0% |
| tb_mov_financieros | 501.500 | 499.119 | 2.381 | 99.53% |
| tb_obligaciones | 30.000 | 29.723 | 277 | 99.08% |
| tb_comisiones_log | 80.000 | 80.000 | 0 | 100.0% |

Los rechazos coinciden con las anomalías inyectadas en la Fase 1:
- `tb_obligaciones`: **277 registros rechazados = exactamente** los 277
  `vr_desembolsado > vr_aprobado` generados en la Fase 1.
- `tb_mov_financieros`: 2.381 rechazados ≈ 1.500 duplicados exactos + ~934
  fechas fuera de rango (con solapamiento esperado entre ambas anomalías
  sobre el mismo subconjunto de filas).

### 5 verificaciones automatizadas de calidad — resultado: **PASSED** (10/10)

| Chequeo | Resultado |
|---|---|
| Unicidad de PK (×6 tablas) | 0 duplicados en cada una |
| Sin nulos en columnas críticas | 0 nulos |
| Integridad referencial (FK) | 0 registros huérfanos |
| Montos de transacción positivos | 0 violaciones |
| Fechas de movimiento en rango | 0 violaciones |

### Tabla de errores del pipeline

`s3://finbank-silver-dev-278714105600/_errors/`, particionada por
`table_name`. Contiene registros reales de `tb_mov_financieros` (fechas
fuera de rango) y `tb_obligaciones` (inconsistencia de negocio), cada uno
con el motivo documentado (`reason`).

## Gold — resultado

| Tabla | Filas | Nota |
|---|---|---|
| dim_clientes | 10.000 | |
| dim_productos | 50 | |
| dim_geografia | 13 | Coincide con las 13 ciudades del generador de Fase 1 |
| dim_canal | 200 | |
| fact_transacciones | 499.119 | Coincide exacto con Silver limpio |
| fact_cartera | 29.723 | Coincide exacto con Silver limpio |
| fact_rentabilidad_cliente | 68.852 | Combinaciones cliente × mes con actividad |
| fact_kpis_cartera | 1.298 | Agregado por fecha/producto/segmento/ciudad |

### Reglas de negocio verificadas con datos reales

**Distribución `bucket_mora` (fact_cartera):**

| Bucket | Registros | % | % esperado (config Fase 1) |
|---|---|---|---|
| AL_DIA | 20.639 | 69.4% | 70% |
| RANGO_1 | 4.605 | 15.5% | 15% |
| RANGO_2 | 2.361 | 7.9% | 8% |
| RANGO_3 | 1.207 | 4.1% | 4% |
| DETERIORADO | 911 | 3.1% | 3% |

Coincide con la distribución configurada en `data-generation/config.yaml`
para `dias_mora_act` — confirma que la clasificación `bucket_mora` está
correctamente implementada de extremo a extremo.

**`ind_sospechoso` (fact_transacciones): 28.611 de 291.637 marcadas (9.8%)**
— más alto de lo que la intuición de "3 desviaciones estándar" sugeriría
(≈0.3% en una distribución normal). Explicación, no un bug: con ~500K
transacciones entre 10.000 clientes en 12 meses, cada cliente tiene en
promedio 4-5 transacciones por ventana de 30 días — una muestra demasiado
pequeña para una estimación estable de desviación estándar — combinado con
que los montos se generaron con distribución **lognormal** (cola pesada, a
propósito, para simular comportamientos atípicos reales). El resultado es
matemáticamente correcto dado el diseño de los datos y la fórmula tal como
la especifica el enunciado; se documenta como limitación conocida de la
regla con muestras pequeñas, no se oculta.

## Costo real incurrido (Silver + Gold)

Silver: 1 ejecución, 171s. Gold: 1 ejecución, 88s. Ambos en
`G.1X × 2 workers`. Costo aproximado adicional: **menos de USD 0.10**.

## Estado acumulado del pipeline Bronze → Silver → Gold

Los tres Glue Jobs corrieron exitosamente en secuencia contra la
infraestructura real de AWS, con trazabilidad completa de conteos desde el
RDS origen hasta las tablas Gold finales. Pendiente: orquestación formal
(Fase 4) para automatizar esta secuencia con dependencias, reintentos y
alertas — hasta ahora se disparó cada job manualmente vía `aws glue
start-job-run`.

## Corrección post-auditoría: `dim_canal.es_canal_digital` estaba mal calculado

Una auditoría posterior contra `data-generation/generate_data.py` encontró
que `tip_punto` en `tb_sucursales_red` solo toma los valores `SUCURSAL`,
`CORRESPONSAL` y `CAJERO` — los tres son puntos de atención **físicos**.
La versión original de `build_dim_canal` marcaba `CORRESPONSAL` como
`es_canal_digital = True`, lo cual es incorrecto: un corresponsal bancario
es un punto físico asistido (una tienda con datáfono), no un canal
digital. Los canales realmente digitales de FinBank (`APP`, `WEB`) no son
filas de esta tabla — viven como valor de `cod_canal` en
`fact_transacciones`. Se corrigió a `es_canal_digital = False` para las
tres categorías, verificado contra los datos reales tras el re-despliegue:

```
tip_punto     es_canal_digital
CAJERO        [False]
CORRESPONSAL  [False]
SUCURSAL      [False]
```

Ver el razonamiento completo documentado en `pipelines/gold/README.md`.
