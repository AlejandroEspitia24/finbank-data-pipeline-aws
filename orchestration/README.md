# Orquestación — Fase 4

## Qué se construyó

Una state machine de AWS Step Functions (`infra/orchestration.tf` +
`orchestration/state_machine.asl.json.tftpl`) que encadena los tres Glue
Jobs del pipeline Medallion con dependencias explícitas:

```
IngestaBronze --> ValidarVolumen (Lambda) --> LimpiezaSilver --> TransformacionGold --> NotificarExito
       |                                              |                   |
       +---------------------- (falla) ---------------+-------------------+--> NotificarFallo --> Fail
```

Un schedule de EventBridge Scheduler (`aws_scheduler_schedule.daily_pipeline_run`)
dispara la ejecución todos los días a las 02:00 hora de Bogotá.

## Decisiones de diseño

### Step Functions (Standard) en vez de Express

El pipeline corre una vez al día. Standard Workflows cobran por transición
de estado (que aquí son pocas: ~7 por ejecución); Express cobra por
duración + memoria y está pensado para alto volumen de invocaciones cortas
(miles por segundo). Para este caso de uso, Standard es más barato y
además da ejecución garantizada exactamente una vez y un historial de 90
días consultable desde la consola — útil para depurar sin ir a CloudWatch.

### Integración `.sync` con Glue en vez de `startJobRun` simple

Se usa `arn:aws:states:::glue:startJobRun.sync` (no la versión sin
`.sync`). Sin `.sync`, Step Functions dispara el job y pasa inmediatamente
al siguiente estado sin esperar a que termine — Silver arrancaría antes de
que Bronze hubiera escrito datos. El sufijo `.sync` hace que Step
Functions haga polling de `glue:GetJobRun` automáticamente y solo avance
cuando el job termina (o falle si el job falla). Es la razón por la que el
rol de Step Functions tiene permiso `glue:GetJobRun`/`GetJobRuns` además de
`StartJobRun`.

### Reintentos con backoff exponencial (3 intentos)

Cada tarea Glue tiene:
```json
"Retry": [{"ErrorEquals": ["States.ALL"], "IntervalSeconds": 30, "MaxAttempts": 3, "BackoffRate": 2.0}]
```
Espera 30s, luego 60s, luego 120s entre reintentos. Cubre fallos
transitorios (throttling de la API de Glue, problemas de red momentáneos
hacia RDS) sin necesidad de intervención manual. Tras 3 intentos fallidos,
pasa a `Catch` → notificación de fallo por SNS → estado `Fail`.

### Validación de volumen: Lambda, no un cuarto Glue Job

La verificación de "volumen anómalo (>30% de desviación vs. últimas 7
ejecuciones)" es una consulta simple sobre JSON pequeños en S3 (los logs
de `write_run_log`), no una transformación de datos a escala. Levantar un
Glue Job (mínimo 2 workers G.1X, ~1-2 min de arranque de sesión Spark) para
esto sería sobre-ingeniería y encarecería cada ejecución diaria sin
necesidad. Una Lambda con `boto3` cuesta prácticamente cero (dentro de la
capa gratuita perpetua de 1M invocaciones/mes) y corre en segundos.

**Es informativa, no bloqueante**: si detecta anomalía, publica una
alerta SNS pero dejar que Silver/Gold continúen. Un volumen distinto al
histórico no es necesariamente un error (puede ser una carga incremental
legítimamente distinta); decidir si detener el pipeline se deja a una
persona revisando la alerta, no a una regla automática ciega.

### Alertas SNS: fallo y éxito, reutilizando el topic ya creado en Fase 2

`NotificarExito` y `NotificarFallo` publican al mismo
`aws_sns_topic.pipeline_alerts` creado en la Fase 2 (ya tiene la
suscripción por correo configurada). No se crea un topic nuevo — un solo
canal de notificaciones es más simple de gestionar y de documentar en la
sustentación.

### EventBridge Scheduler en vez de EventBridge Rule (cron clásico)

EventBridge Scheduler es el servicio recomendado por AWS para
programación desde 2023 (reemplaza el patrón `aws_cloudwatch_event_rule`
+ `aws_cloudwatch_event_target` para este caso de uso). Soporta zona
horaria nativa (`schedule_expression_timezone`) sin tener que convertir el
cron a UTC a mano, y `flexible_time_window` explícito documenta la
intención de que la hora sea exacta (no hay ventana de tolerancia).

### Batch ID independiente por capa (sin passthrough entre jobs)

Cada Glue Job (Bronze/Silver/Gold) genera su propio `batch_id` (UUID)
internamente — no se pasa un `batch_id` compartido a través de los
parámetros de Step Functions. Esto es intencional: Silver y Gold siempre
leen el **último snapshot completo** de la capa anterior (no un batch
específico), así que no hay necesidad de correlacionar por batch entre
capas. Si en el futuro se necesitara trazabilidad estricta batch-a-batch,
ese sería el punto a cambiar.

## Logs y observabilidad

- Ejecuciones de la state machine: consola de Step Functions o
  `aws stepfunctions get-execution-history`.
- Logs estructurados de la state machine: log group
  `/aws/vendedlogs/states/finbank-dev` (creado en Fase 2/`cloudwatch.tf`,
  nivel `ALL` — incluye datos de entrada/salida de cada estado).
- Logs de la Lambda de validación de volumen:
  `/aws/lambda/finbank-dev-volume-anomaly`.
- Dashboard consolidado: `aws_cloudwatch_dashboard.pipeline`
  (`infra/cloudwatch.tf`), con un widget de las últimas 50 líneas de log
  de Step Functions.

## Cómo probar manualmente

```bash
aws stepfunctions start-execution \
  --state-machine-arn "$(terraform -chdir=infra output -raw state_machine_arn)" \
  --profile prueba-tecnica-finbank
```
