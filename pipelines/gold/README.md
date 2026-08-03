# Capa Gold — Modelo dimensional y reglas de negocio

## Tablas producidas

| Tabla | Tipo | Origen (Silver) |
|---|---|---|
| `dim_clientes` | Dimensión | tb_clientes_core |
| `dim_productos` | Dimensión | tb_productos_cat |
| `dim_geografia` | Dimensión | tb_sucursales_red |
| `dim_canal` | Dimensión | tb_sucursales_red |
| `fact_transacciones` | Hecho | tb_mov_financieros |
| `fact_cartera` | Hecho | tb_obligaciones |
| `fact_rentabilidad_cliente` | Hecho | tb_comisiones_log + tb_obligaciones + tb_productos_cat |
| `fact_kpis_cartera` | KPI ejecutivo (agregación) | fact_cartera + dim_clientes |

## Linaje de campos calculados (mínimo 3 exigidos por el enunciado)

| Campo | Tabla destino | Tabla(s) de origen | Transformación | Propósito de negocio |
|---|---|---|---|---|
| `bucket_mora` | fact_cartera | tb_obligaciones.dias_mora_act | `CASE` de 5 rangos (Al día, R1 1-30, R2 31-60, R3 61-90, Deteriorado >90) | Clasificar el riesgo de cada obligación para el equipo de Riesgo Crediticio |
| `provision_estimada` | fact_cartera | tb_obligaciones.sdo_capital × tabla de provisión por bucket_mora | `sdo_capital * PROVISION_PCT[bucket_mora]` | Estimar la provisión regulatoria exigida por la Superintendencia Financiera |
| `ind_sospechoso` | fact_transacciones | tb_mov_financieros.vr_mov (calculado en Silver, propagado a Gold) | `vr_mov > promedio_30d + 3 * desviación_estándar_30d` (ventana por cliente) | Alimentar el motor de reglas de prevención de fraude |
| `cltv_12m` | fact_rentabilidad_cliente | tb_comisiones_log + tb_obligaciones (interés estimado) | Suma móvil de 12 meses de `ingreso_interes + ingreso_comisiones` por cliente | Customer Lifetime Value para decisiones comerciales |
| `vr_mov_usd` | fact_transacciones | tb_mov_financieros.vr_mov | `vr_mov / USD_COP_RATE` (tasa fija documentada) | Estandarizar montos a USD para reportes regionales multi-país |

## Supuestos documentados (declaración obligatoria ante ambigüedad del enunciado)

**Tasa de cambio COP→USD fija (`USD_COP_RATE = 4000`).** El dataset
sintético no genera una tabla de tasas de cambio históricas. Se usa un valor
fijo razonable, documentado explícitamente en el código
(`gold_transform.py`), en vez de inventar una tabla de tasas diarias que el
enunciado no pidió.

**Ingreso por intereses estimado, no observado directamente.** El esquema
origen (Fase 1) no genera movimientos con `tip_mov = 'INTERES'` — las
categorías de movimiento son COMPRA/PAGO/TRANSFERENCIA/AVANCE/RECARGA. Por
lo tanto, `fact_rentabilidad_cliente` estima el ingreso por intereses como
`saldo_capital_vigente × tasa_mensual_equivalente_del_producto`, en vez de
sumar movimientos de tipo "interés" que no existen en los datos. Es la
interpretación más razonable disponible dado el modelo de datos generado en
la Fase 1.

**Tabla de provisión por bucket de mora.** El enunciado pide "provisión
estimada según tabla regulatoria" sin especificar los porcentajes exactos.
Se usan valores inspirados en la normativa colombiana de provisión de
cartera de consumo (1% / 5% / 20% / 50% / 100% por bucket), documentados
como supuesto y fácilmente ajustables (`PROVISION_PCT` en el código).

## Particionamiento (optimización de consultas, exigido por el enunciado)

- `fact_transacciones`: particionada por `anio`/`mes` (fecha de negocio) — es
  el filtro más común en análisis de transacciones y reportes regulatorios.
- `fact_cartera`: particionada por `bucket_mora` — el equipo de Riesgo
  consulta constantemente "solo la cartera en mora" o "solo deteriorada".
