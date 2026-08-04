# Evidencia — Fase 4 / Orquestación con Step Functions

## Infraestructura desplegada

| Recurso | Nombre |
|---|---|
| State machine | `finbank-dev-pipeline` |
| Lambda de validación de volumen | `finbank-dev-volume-anomaly` |
| Schedule (EventBridge Scheduler) | `finbank-dev-daily-run` — `cron(0 2 * * ? *)`, zona horaria `America/Bogota` |
| Rol de Step Functions | `finbank-dev-stepfunctions-role` (reutilizado de Fase 2, ampliado con permiso `lambda:InvokeFunction`) |
| Topic SNS | `finbank-dev-pipeline-alerts` (reutilizado de Fase 2) |

Desplegado vía `terraform apply` (8 recursos nuevos, 1 modificado, 0
destruidos) contra la cuenta AWS real `278714105600`.

## Ejecución end-to-end real

Ejecución disparada manualmente vía
`aws stepfunctions start-execution` para verificar el flujo completo antes
de dejarlo en manos del schedule automático:

```
arn:aws:states:us-east-1:278714105600:execution:finbank-dev-pipeline:99c2e149-a63f-4636-8d4c-848866bac8b0
```

| Estado | Inicio | Fin | Duración |
|---|---|---|---|
| `IngestaBronze` | 19:33:58 | 19:35:56 | 1m 58s |
| `ValidarVolumen` (Lambda) | 19:35:56 | 19:35:59 | 3s |
| `LimpiezaSilver` | 19:35:59 | 19:39:48 | 3m 49s |
| `TransformacionGold` | 19:39:48 | 19:42:56 | 3m 8s |
| `NotificarExito` (SNS) | 19:42:56 | 19:42:56 | <1s |
| **Total** | | | **8m 58s** |

**Resultado: `SUCCEEDED`** — las 4 tareas encadenadas corrieron en el
orden correcto, cada una esperando a que la anterior terminara realmente
(gracias a la integración `.sync` con Glue), sin intervención manual entre
pasos.

## DQ checks (Silver) de esta ejecución: 10/10 PASSED

Mismo resultado que en la Fase 3 (ver `evidencia-fase3-silver-gold.md`),
confirmando que la orquestación automática produce el mismo resultado de
calidad que las ejecuciones manuales anteriores.

## Hallazgo real: alerta de volumen anómalo — explicado, no un bug

La Lambda `ValidarVolumen` **sí detectó y alertó** una anomalía en esta
ejecución:

```json
{
  "date": "2026-08-04",
  "records_today": 10250,
  "history_days_used": 1,
  "anomaly_detected": true,
  "avg_last_n_days": 621750.0,
  "deviation_pct": 98.35
}
```

**Por qué es correcto, no un error:** el pipeline usa carga incremental
por *watermark* para las 3 tablas de mayor volumen
(`tb_mov_financieros`, `tb_obligaciones`, `tb_comisiones_log`) — la
primera ejecución de Bronze (Fase 3) ya las cargó por completo y avanzó el
watermark hasta el final de los datos disponibles en RDS. Como no se
insertó ningún dato nuevo en RDS entre la Fase 3 y esta ejecución, las 3
tablas incrementales correctamente **no encontraron filas nuevas**
(`status: SUCCESS_NO_NEW_DATA`, `records_processed: 0`). Las 3 tablas de
carga completa (`full`) sí se re-cargaron enteras:

| Tabla | Modo | Registros hoy |
|---|---|---|
| tb_clientes_core | full | 10.000 |
| tb_productos_cat | full | 50 |
| tb_sucursales_red | full | 200 |
| tb_mov_financieros | incremental | 0 (`SUCCESS_NO_NEW_DATA`) |
| tb_obligaciones | incremental | 0 (`SUCCESS_NO_NEW_DATA`) |
| tb_comisiones_log | incremental | 0 (`SUCCESS_NO_NEW_DATA`) |
| **Total** | | **10.250** — coincide exacto con `records_today` |

El promedio histórico usado por la Lambda (621.750) es el volumen de la
**primera carga completa** de la Fase 3 (todas las tablas full-load). Es
matemáticamente esperable que la segunda ejecución, siendo incremental
sobre datos sin cambios, tenga muchísimo menos volumen — la alerta hizo
exactamente lo que debía hacer: avisar de una desviación real y grande,
sin necesidad de que una persona adivine que es "normal" hasta
investigarlo. En un escenario con carga de datos real y continua a RDS,
este mismo mecanismo detectaría, por ejemplo, una interrupción real en el
proceso de origen (0 filas nuevas cuando se esperaban miles).

La alerta se publicó al topic SNS (`SdkResponseMetadata` con
`HttpStatusCode: 200` confirmado en el output de `NotificarExito`), y el
pipeline **continuó** hacia Silver y Gold sin bloquearse, tal como está
diseñado (ver `orchestration/README.md`).

## Corrección post-auditoría: contenido real de las notificaciones

Una auditoría contra el enunciado completo detectó que las notificaciones
originales (`NotificarExito`/`NotificarFallo`) eran mensajes genéricos sin
los datos que el enunciado exige explícitamente. Se corrigió:

**Reporte de éxito** — ahora incluye registros procesados por capa, tiempo
total de ejecución y alertas de calidad, calculados por una Lambda nueva
(`finbank-dev-execution-summary`) que lee los `run_logs`/`quality_report`/
`dq_checks` reales de S3. Verificado con una ejecución real (`SUCCEEDED`):

```json
{"date":"2026-08-04","bronze_records":20500,"silver_records":1238190,
 "gold_records":1218516,"quality_rejected_records":0,"dq_checks_failed":0,
 "execution_duration_seconds":416}
```

Nota: `silver_records`/`gold_records` sumaron dos ejecuciones manuales
corridas el mismo día UTC (esta y la de la sección anterior), porque la
agregación es por fecha, no por ejecución individual — coherente con que
el pipeline está diseñado para correr una sola vez al día vía el schedule;
en producción real este número reflejaría una sola ejecución.

**Alerta de fallo** — ahora incluye el nombre del DAG, la tarea específica
que falló, la capa afectada, la hora exacta del fallo y el mensaje de
error completo. Verificado con `aws stepfunctions test-state`
(`--inspection-level TRACE`) sobre el estado real `NotificarFallo`, sin
tocar infraestructura:

```
Fallo el pipeline Medallion FinBank.
DAG (state machine): finbank-dev-pipeline
Ejecucion: c634944b-19fc-4144-9807-960d9da89a8f
Tarea que fallo: LimpiezaSilver
Capa afectada: Silver
Hora del fallo (UTC): 2026-08-04T01:56:46.397Z
Error: States.TaskFailed
Causa: Glue job finbank-dev-silver-clean failed: Job run terminated with status FAILED
```

## Evidencia de correo real recibido (cierre del hallazgo #4 de la auditoría)

La suscripción de correo se confirmó (`aws sns list-subscriptions-by-topic`
ya no muestra `PendingConfirmation`, sino un `SubscriptionArn` real). Con
la suscripción activa se generaron los dos correos reales que exige el
enunciado:

**Correo de fallo de prueba** — disparado con
`aws stepfunctions test-state` sobre el estado real `NotificarFallo`
(mismo mecanismo usado para verificar el formato del mensaje, ahora con
entrega real habilitada). Asunto: *"FinBank Pipeline - FALLO en tarea
LimpiezaSilver"*, con el detalle completo (tarea, capa, hora UTC, error,
causa) — ver el contenido exacto en la sección de corrección más arriba.

**Correo de resumen diario de éxito** — ejecución real completa
(`arn:aws:states:...:execution:finbank-dev-pipeline:deee2a7d-...`),
`SUCCEEDED` en 6m58s (21:11:20 → 21:18:18), con el resumen:

```json
{"date":"2026-08-04","bronze_records":30750,"silver_records":1857285,
 "gold_records":1827774,"quality_rejected_records":0,"dq_checks_failed":0,
 "execution_duration_seconds":418}
```

Ambos mensajes se publicaron exitosamente al topic (`HttpStatusCode: 200`
en ambas respuestas de SNS) con la suscripción de correo ya confirmada
(`johan.espitia.c@gmail.com`). Pendiente: adjuntar aquí la captura de
pantalla de ambos correos desde la bandeja de entrada — es el único paso
que queda 100% en manos del usuario, ya que el agente no tiene acceso al
cliente de correo.

## Costo real incurrido (Fase 4)

- Step Functions: 5 transiciones de estado por ejecución — costo
  insignificante (fracciones de centavo, dentro del free tier de 4.000
  transiciones/mes).
- Lambda: 1 invocación, 128MB, ~3s — dentro del free tier perpetuo (1M
  invocaciones/mes).
- EventBridge Scheduler: sin costo por el schedule en sí.
- Glue (Bronze+Silver+Gold, esta ejecución): ~9 minutos totales en
  `G.1X × 2 workers` — costo aproximado menor a USD 0.15.
