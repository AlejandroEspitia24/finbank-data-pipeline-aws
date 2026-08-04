# Prueba Técnica — Ingeniero de Datos (DataKnow)

## Decisiones iniciales (declaración obligatoria)

- **Sector / escenario elegido:** Escenario A — Banca y Servicios Financieros (FinBank S.A.)
- **Plataforma cloud:** Amazon Web Services (AWS)
- **Justificación del sector:** mayor afinidad con dominio financiero (mora, riesgo, fraude, CLTV) y reglas de negocio bien acotadas y medibles.
- **Justificación de la plataforma:** capa gratuita permanente amplia (S3, Lambda, Glue Data Catalog), USD 300 de crédito en los primeros 90 días, y el stack Glue + Step Functions + S3 permite construir la arquitectura Medallion completa de forma 100% serverless, minimizando el riesgo de gastos inesperados en una cuenta de prueba.
- **Herramienta de IaC:** Terraform (backend remoto de estado en S3 + DynamoDB para locking)
- **Motor de procesamiento:** AWS Glue (PySpark, serverless)
- **Orquestador:** AWS Step Functions (con notificaciones vía SNS)
- **Base de datos origen:** Amazon RDS PostgreSQL

> **Estado del repositorio: completo.** Las 5 fases del pipeline están
> implementadas, desplegadas y verificadas contra AWS real (cuenta
> `278714105600`, región `us-east-1`): generación de datos → infraestructura
> como código → pipeline Medallion (Bronze/Silver/Gold) → orquestación con
> Step Functions → gobierno y seguridad. Además del desarrollo fase a fase,
> se hizo una auditoría final completa contra el enunciado original (no solo
> contra el propio plan) que encontró y corrigió 4 hallazgos reales — ver
> la sección "Auditoría final" más abajo.

## Arquitectura

```
RDS PostgreSQL (origen)
        │  (Glue JDBC Connection)
        ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   BRONZE    │──▶│   SILVER    │──▶│    GOLD     │
│ (S3/Parquet)│   │ (S3/Parquet)│   │ (S3/Parquet)│
│ copia cruda │   │ limpieza +  │   │  modelo     │
│ + auditoría │   │ FK + PII +  │   │ dimensional │
│             │   │ calidad     │   │ + reglas    │
└─────────────┘   └─────────────┘   └─────────────┘
        ▲                 ▲                 ▲
        └─────────────────┴─────────────────┘
              orquestado por AWS Step Functions
        (reintentos, alertas SNS, EventBridge Scheduler diario)

Gobierno transversal: Secrets Manager, IAM least-privilege por servicio,
3 roles humanos (Ingeniero de Datos / Analista / Administrador), CloudTrail
(management + data events), AWS Budget.
```

Detalle completo de la arquitectura, el modelo de datos de FinBank y el
cronograma de desarrollo en [`docs/PLAN.md`](docs/PLAN.md).

## Cómo desplegar y ejecutar todo (reproducible de punta a punta)

1. **Generar y cargar los datos sintéticos** — ver
   [`data-generation/README.md`](data-generation/README.md):
   ```bash
   cd data-generation
   pip install -r requirements.txt
   cp .env.example .env   # completar credenciales de tu Postgres local/Docker
   python generate_data.py
   python load_to_postgres.py
   ```
2. **Desplegar la infraestructura AWS** — instrucciones completas y
   reproducibles en [`infra/README.md`](infra/README.md) (bootstrap del
   backend remoto → variables → `terraform apply` → confirmar SNS →
   cargar los datos de la Fase 1 al RDS real).
3. **Ejecutar el pipeline manualmente** (además de la ejecución
   automática diaria a las 02:00 hora de Bogotá vía EventBridge
   Scheduler):
   ```bash
   aws stepfunctions start-execution \
     --state-machine-arn "$(terraform -chdir=infra output -raw state_machine_arn)" \
     --profile <tu-perfil-aws>
   ```
4. **Consultar resultados**: dashboard de CloudWatch
   (`terraform -chdir=infra output -raw cloudwatch_dashboard_url`),
   historial de ejecuciones en la consola de Step Functions, o
   directamente los Parquet de Gold vía Athena/`aws s3 ls`.

## Estructura del repositorio

| Carpeta / archivo | Contenido |
|---|---|
| `/infra` | Código Terraform completo (S3, RDS, Glue, Step Functions, Lambda, IAM, Secrets Manager, SNS, CloudWatch, CloudTrail, Budget) — ver `infra/README.md` |
| `/data-generation` | Scripts de generación de datos sintéticos + archivo de configuración (YAML) |
| `/pipelines` | Código de transformación Bronze → Silver → Gold (Glue jobs PySpark), un README por capa con el detalle de cada decisión |
| `/orchestration` | Definición de la state machine de Step Functions (ASL) + funciones Lambda de soporte (validación de volumen, resumen de ejecución) |
| `/docs` | Plan del proyecto, diagrama ER, catálogo de datos (campo por campo), y evidencia de ejecución real de cada fase |
| `CHANGELOG.md` | Historial de cambios con fecha, autor y descripción |

## Evidencia de ejecución por fase

Cada fase tiene un documento de evidencia con resultados reales contra AWS
(no solo código): comandos ejecutados, salidas de consola, conteos de
filas verificados entre capas.

| Fase | Evidencia |
|---|---|
| 1 — Generación de datos y modelo relacional | [`docs/evidencia-fase1-carga.md`](docs/evidencia-fase1-carga.md), [`docs/er-diagram.md`](docs/er-diagram.md) |
| 2 — Infraestructura como código | [`docs/evidencia-fase2-infra.md`](docs/evidencia-fase2-infra.md) |
| 3 — Pipeline Medallion (Bronze) | [`docs/evidencia-fase3-bronze.md`](docs/evidencia-fase3-bronze.md) |
| 3 — Pipeline Medallion (Silver/Gold) | [`docs/evidencia-fase3-silver-gold.md`](docs/evidencia-fase3-silver-gold.md) |
| 4 — Orquestación con Step Functions | [`docs/evidencia-fase4-orquestacion.md`](docs/evidencia-fase4-orquestacion.md) |
| 5 — Gobierno, seguridad y calidad | [`docs/evidencia-fase5-gobernanza.md`](docs/evidencia-fase5-gobernanza.md) |
| Catálogo de datos (campo por campo) | [`docs/catalogo-datos.md`](docs/catalogo-datos.md) |

## Auditoría final contra el enunciado

Antes de dar por cerrado el desarrollo, se releyó el enunciado original
completo (no solo el plan propio) y se verificó cada entregable exigido
contra el texto exacto. Se encontraron y corrigieron 4 hallazgos reales,
documentados con causa raíz y verificación contra AWS real en los
documentos de evidencia de las Fases 3, 4 y 5 (buscar la sección
"Corrección post-auditoría" en cada uno):

1. Las notificaciones de Step Functions no incluían la información exigida
   (tarea/capa/hora del fallo; registros por capa/tiempo/alertas del
   éxito) — corregido con una Lambda de resumen y manejo de fallo por
   tarea en la state machine.
2. CloudTrail solo auditaba infraestructura, no acceso a datos — se
   agregaron *data events* de S3 en los 3 buckets del Data Lake.
3. Un campo calculado en Gold (`dim_canal.es_canal_digital`) tenía un
   error de lógica de negocio (marcaba un canal físico como digital) —
   corregido y verificado contra los datos reales.
4. Falta de evidencia real de las alertas por correo — resuelto tras
   confirmar la suscripción SNS y generar ambos correos reales (fallo de
   prueba y resumen de éxito).

## Plan del proyecto

Ver el detalle completo de fases, cronograma y decisiones técnicas en [`docs/PLAN.md`](docs/PLAN.md).
