# Evidencia — Fase 1: Generación de datos y carga en base de datos relacional

Prueba realizada localmente contra PostgreSQL 16 en Docker (misma imagen/motor
que Amazon RDS PostgreSQL usará en la Fase 2), para validar `schema.sql` y
`load_to_postgres.py` antes de desplegar infraestructura real en AWS.

## Generación (`python generate_data.py --config config.yaml`)

```
2026-08-02 19:13:48 | INFO | Iniciando generación | semilla=42 | rango histórico=2025-08-02 a 2026-08-02
2026-08-02 19:13:52 | INFO | Anomalía 1/3: 1500 transacciones duplicadas inyectadas en TB_MOV_FINANCIEROS
2026-08-02 19:13:52 | INFO | Anomalía 2/3: 934 fechas fuera de rango inyectadas en TB_MOV_FINANCIEROS
2026-08-02 19:13:52 | INFO | Anomalía 3/3: 277 obligaciones con vr_desembolsado > vr_aprobado inyectadas
2026-08-02 19:13:52 | INFO | Inyectando ~5% de nulos en columnas no críticas...
  tb_productos_cat             50 filas
  tb_sucursales_red           200 filas
  tb_clientes_core         10,000 filas
  tb_mov_financieros      501,500 filas
  tb_obligaciones          30,000 filas
  tb_comisiones_log        80,000 filas
```

## Carga (`python load_to_postgres.py`) — `SELECT COUNT(*)` por tabla

```
Esquema aplicado (schema.sql)
  Cargada tb_productos_cat             50 filas
  Cargada tb_sucursales_red           200 filas
  Cargada tb_clientes_core         10,000 filas
  Cargada tb_mov_financieros      501,500 filas
  Cargada tb_obligaciones          30,000 filas
  Cargada tb_comisiones_log        80,000 filas

Verificación de carga (SELECT COUNT(*)):
  tb_productos_cat             50 filas
  tb_sucursales_red           200 filas
  tb_clientes_core         10,000 filas
  tb_mov_financieros      501,500 filas
  tb_obligaciones          30,000 filas
  tb_comisiones_log        80,000 filas
```

## Validaciones de calidad ejecutadas sobre los datos generados

| Validación | Resultado |
|---|---|
| Registros huérfanos `mov.id_cli` → `clientes.id_cli` | 0 |
| Registros huérfanos `mov.cod_prod` → `productos.cod_prod` | 0 |
| Registros huérfanos `obligaciones.id_cli` → `clientes.id_cli` | 0 |
| Registros huérfanos `comisiones.id_cli` → `clientes.id_cli` | 0 |
| % nulos en `clientes.depto_res` | 5.1% |
| % nulos en `clientes.score_buro` | 5.2% |
| % nulos en `mov.id_dispositivo` | 5.0% |
| Duplicados exactos `id_mov` (anomalía 1) | 1,500 (coincide con log) |
| `vr_desembolsado > vr_aprobado` (anomalía 3) | 277 (coincide con log) |
| Edad de clientes: media / desv. estándar | 38.2 años / 11.5 (≈ N(38,12) esperado) |
| Distribución `dias_mora_act` | Al día: 20.821 · R1: 4.650 · R2: 2.386 · R3: 1.219 · Deteriorado: 924 |

> Nota: esta corrida usó un contenedor Docker Postgres efímero solo para
> validación local; no representa la infraestructura final de AWS (RDS), que
> se aprovisiona en la Fase 2 vía Terraform. Cuando la Fase 2 esté lista,
> `load_to_postgres.py` se ejecuta sin cambios apuntando al endpoint real de
> RDS mediante las variables de entorno en `.env`.
