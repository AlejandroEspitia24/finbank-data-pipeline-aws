# Plan del Proyecto — FinBank End-to-End Data Pipeline (AWS)

## 1. Contexto del negocio

FinBank S.A., banco digital en 5 países de Latinoamérica. Necesita consolidar datos dispersos
de riesgo crediticio, fraude, rentabilidad de cliente y reportes regulatorios, hoy resueltos
con reportes manuales en Excel.

### Necesidades de negocio a resolver

1. Indicador diario de mora por cliente, producto y región.
2. Detección automática de transacciones atípicas (posible fraude).
3. CLTV mensual por cliente (intereses + comisiones - incentivos).
4. Insumos para reportes regulatorios (cuentas activas, transacciones, volúmenes).
5. Vista consolidada de cliente para el equipo comercial.

## 2. Arquitectura general

```
RDS PostgreSQL (origen)
        │  extracción (Glue Job JDBC)
        ▼
   S3 Bronze  (Parquet, esquema crudo + metadatos de auditoría, particionado por fecha ingesta)
        │  Glue Job PySpark — limpieza, tipado, enmascaramiento PII, validación referencial
        ▼
   S3 Silver  (Parquet, datos limpios y conformados, tabla de errores, reporte de calidad)
        │  Glue Job PySpark — reglas de negocio, modelo dimensional
        ▼
   S3 Gold    (Parquet particionado, dim_* y fact_*, KPIs ejecutivos)
        │
        ▼
Glue Data Catalog + Athena (consumo analítico) / QuickSight opcional
```

Orquestación: **Step Functions** state machine (Extract → Bronze → Silver → Gold → Data
Quality checks → Notificación SNS). Ejecución programada diaria (EventBridge Scheduler, 02:00
hora local) con reintentos (backoff exponencial, 3 intentos) y alertas por SNS (email) en fallo,
éxito diario y anomalías de volumen.

Seguridad: IAM roles de mínimo privilegio por componente (rol de Glue Bronze, Silver, Gold,
Step Functions, rol "Analista" solo lectura Gold), Secrets Manager para credenciales de RDS,
KMS para cifrado de S3, enmascaramiento/hash de PII (`num_doc`, etc.) desde Silver en adelante.

## 3. Modelo de datos

### 3.1 Fuentes (RDS PostgreSQL — capa transaccional simulada)

| Tabla origen | Volumen mínimo | Campos clave |
|---|---|---|
| `TB_CLIENTES_CORE` | 10.000 | id_cli, nomb_cli, apell_cli, tip_doc, num_doc, fec_nac, fec_alta, cod_segmento, score_buro, ciudad_res, depto_res, estado_cli, canal_adquis |
| `TB_PRODUCTOS_CAT` | 50 | cod_prod, desc_prod, tip_prod, tasa_ea, plazo_max_meses, cuota_min, comision_admin, estado_prod |
| `TB_MOV_FINANCIEROS` | 500.000 | id_mov, id_cli, cod_prod, num_cuenta, fec_mov, hra_mov, vr_mov, tip_mov, cod_canal, cod_ciudad, cod_estado_mov, id_dispositivo |
| `TB_OBLIGACIONES` | 30.000 | id_oblig, id_cli, cod_prod, vr_aprobado, vr_desembolsado, sdo_capital, vr_cuota, fec_desembolso, fec_venc, dias_mora_act, num_cuotas_pend, calif_riesgo |
| `TB_SUCURSALES_RED` | 200 | cod_suc, nom_suc, tip_punto, ciudad, depto, latitud, longitud, activo |
| `TB_COMISIONES_LOG` | 80.000 | id_comision, id_cli, cod_prod, fec_cobro, vr_comision, tip_comision, estado_cobro |

### 3.2 Capa Gold (modelo dimensional)

| Tabla destino | Origen | Transformaciones clave |
|---|---|---|
| `dim_clientes` | TB_CLIENTES_CORE | nombre completo, edad desde fec_nac, etiqueta de segmento legible |
| `dim_productos` | TB_PRODUCTOS_CAT | nombres de negocio, tasa mensual equivalente, familia (crédito/ahorro/transaccional) |
| `dim_geografia` / `dim_canal` | TB_SUCURSALES_RED | separación en 2 dimensiones: ciudad/depto y tipo de punto/canal digital |
| `fact_transacciones` | TB_MOV_FINANCIEROS | validación FK contra dim_clientes, monto a USD, flag horario hábil/no hábil, promedio móvil 30d, `ind_sospechoso` (calculado en Silver) |
| `fact_cartera` | TB_OBLIGACIONES | `bucket_mora` (5 rangos), `calif_riesgo` A-E, provisión estimada |
| `fact_rentabilidad_cliente` | TB_COMISIONES_LOG + TB_MOV_FINANCIEROS | ingreso total mensual, CLTV = suma histórica 12 meses |
| `fact_kpis_cartera` (tabla KPI ejecutiva) | fact_cartera | agregada por fecha, producto, segmento, ciudad: obligaciones activas, monto cartera, monto en mora, tasa de mora, clientes en mora |

### 3.3 Reglas de negocio a implementar (Gold)

- `bucket_mora`: Al día (0), Rango 1 (1-30), Rango 2 (31-60), Rango 3 (61-90), Deteriorado (>90).
- `ind_sospechoso` (Silver): `vr_mov` > 3 desviaciones estándar del promedio móvil de 30 días del mismo cliente.
- CLTV mensual = suma de intereses + comisiones efectivamente cobradas, últimos 12 meses calendario.
- `fact_kpis_cartera`: total obligaciones activas, monto total cartera, monto en mora, tasa de mora (%), clientes con alguna obligación en mora — agregado por fecha/producto/segmento/ciudad.

## 4. Fases y entregables

### Fase 1 — Generación de datos y modelo relacional
- Script Python (`data-generation/`) con librería `faker` + `numpy`/`pandas`, semilla fija, config YAML (volumen, rango de fechas, semilla).
- Distribuciones realistas (edades ~normal, montos según tipo de movimiento, concentración horaria en horas hábiles).
- Integridad referencial garantizada por generación (FKs válidas).
- ~5% de nulos controlados en campos no críticos.
- Al menos 3 anomalías intencionales documentadas (duplicados, fechas fuera de rango, campos inconsistentes).
- Salida en al menos 2 formatos (CSV + Parquet).
- Script de carga a RDS PostgreSQL.
- Diagrama ER en `/docs`, evidencia de carga (`SELECT COUNT(*)` por tabla).

### Fase 2 — Infraestructura como código (Terraform, `/infra`)
- Backend remoto de estado (S3 + DynamoDB lock).
- Recursos: RDS PostgreSQL, S3 (bronze/silver/gold separados), Glue Database + Crawlers, roles IAM de mínimo privilegio, CloudWatch Log Groups, SNS Topic, Secrets Manager.
- Variables parametrizadas (región, nombres, tamaños), sin credenciales en código.
- Workspaces o var-files para `dev`/`prod`.
- Outputs con ARNs/nombres de recursos.

### Fase 3 — Pipeline Medallion (`/pipelines`)
- **Bronze:** Glue Job JDBC → Parquet crudo, metadatos de auditoría (timestamp ingesta, sistema fuente, batch id), particionado año/mes/día, log de ejecución, soporte de carga incremental.
- **Silver:** deduplicación, tipado, `ind_sospechoso`, validación de integridad referencial (tabla de errores), estrategia de nulos documentada, enmascaramiento/hash de PII, reporte de calidad por ejecución.
- **Gold:** dims + facts con reglas de negocio, ≥3 tablas/vistas de agregación, particionado/optimización, linaje documentado (≥3 campos calculados), tabla de KPIs ejecutivos.
- Idempotencia y manejo de errores centralizado (tabla de errores del pipeline).
- ≥5 validaciones de calidad automatizadas (Great Expectations o custom).

### Fase 4 — Orquestación (`/orchestration`)
- State machine de Step Functions: Extract → Bronze → Silver → Gold → DQ checks → notificación.
- Dependencias explícitas (Silver solo si Bronze ok, Gold solo si Silver ok).
- EventBridge Scheduler diario 02:00, reintentos con backoff exponencial (3 intentos), timeout por tarea.
- Alertas SNS: fallo de tarea, resumen diario de éxito, anomalía de volumen (>30% desviación vs promedio 7 ejecuciones).
- Dashboard/log de monitoreo accesible (CloudWatch Dashboard).

### Fase 5 — Gobierno, seguridad y calidad
- 3 roles IAM: Ingeniero de Datos (lectura/escritura todas las capas), Analista (solo lectura Gold), Administrador (control total).
- Principio de mínimo privilegio por componente (roles de servicio dedicados).
- Secretos en Secrets Manager, sin credenciales en código/config.
- Auditoría de accesos (CloudTrail).
- Catálogo de datos básico en Markdown (`/docs`) — tablas Silver/Gold, tipo, origen, sensibilidad.
- CHANGELOG.md con historial de cambios.

## 5. Cronograma tentativo (7 días hábiles)

| Día | Foco |
|---|---|
| 1 | Fase 1 completa: generación de datos, carga a RDS, diagrama ER |
| 2 | Fase 2: Terraform completo, despliegue de infraestructura base |
| 3-4 | Fase 3: pipeline Bronze → Silver → Gold, reglas de negocio, calidad de datos |
| 5 | Fase 4: orquestación con Step Functions, alertas, ejecución programada |
| 6 | Fase 5: roles, seguridad, catálogo de datos, pruebas de idempotencia |
| 7 | Pulido de README, evidencias, CHANGELOG, revisión final y entrega |

## 6. Riesgos y mitigaciones

- **Costos inesperados en cuenta AWS de prueba:** usar solo instancias t2/t3.micro, Glue serverless, presupuesto de alerta a USD 5-10, apagar/destruir recursos (`terraform destroy`) entre sesiones de trabajo si no se está desarrollando activamente.
- **Tiempo limitado (7 días hábiles):** priorizar Fases 1-3 (obligatorias y con más peso evaluativo) antes de invertir tiempo extra en Fase 5.
- **Alcance del scope de reglas de negocio:** documentar cualquier supuesto de interpretación directamente en el README, según indica el enunciado.

## 7. Próximos pasos

Con el plan aprobado, el siguiente paso es iniciar la Fase 1 (generación de datos sintéticos y
modelo relacional).
