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

> Estado actual del repositorio: **Fase 3 completada** (pipeline Medallion Bronze → Silver → Gold funcionando de extremo a extremo en AWS). El desarrollo se irá documentando fase a fase según el plan en [`docs/PLAN.md`](docs/PLAN.md).

## Estructura del repositorio

| Carpeta / archivo | Contenido |
|---|---|
| `/infra` | Código Terraform completo (S3, Glue, RDS, IAM, Secrets Manager, SNS, CloudWatch) |
| `/data-generation` | Scripts de generación de datos sintéticos + archivo de configuración (YAML) |
| `/pipelines` | Código de transformación Bronze → Silver → Gold (Glue jobs PySpark) |
| `/orchestration` | Definición del Step Functions state machine |
| `/docs` | Diagrama ER, diagrama de arquitectura, catálogo de datos, plan del proyecto |
| `CHANGELOG.md` | Historial de cambios del proyecto |

## Plan del proyecto

Ver el detalle completo de fases, cronograma y decisiones técnicas en [`docs/PLAN.md`](docs/PLAN.md).
