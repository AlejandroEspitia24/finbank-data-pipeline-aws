# Evidencia — Fase 2: Infraestructura como Código (Terraform / AWS)

## Despliegue exitoso (`terraform apply`)

Cuenta AWS: `278714105600` · Región: `us-east-1` · Entorno: `dev`

```
Apply complete! Resources: 34 added, 0 changed, 0 destroyed.  (infra/, primer apply)
Apply complete! Resources: 5 added, 0 changed, 0 destroyed.   (infra/bootstrap/)

Outputs:
cloudwatch_dashboard_url = "https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=finbank-dev-pipeline"
glue_database_name       = "finbank_dev_catalog"
glue_role_arn             = "arn:aws:iam::278714105600:role/finbank-dev-glue-role"
rds_endpoint              = "finbank-dev.ca9kgwuuu2sa.us-east-1.rds.amazonaws.com:5432"
rds_secret_arn            = "arn:aws:secretsmanager:us-east-1:278714105600:secret:finbank/dev/rds/credentials-urT0Fn"
s3_bucket_names           = {
  bronze = "finbank-bronze-dev-278714105600"
  gold   = "finbank-gold-dev-278714105600"
  silver = "finbank-silver-dev-278714105600"
}
sns_topic_arn             = "arn:aws:sns:us-east-1:278714105600:finbank-dev-pipeline-alerts"
step_functions_role_arn   = "arn:aws:iam::278714105600:role/finbank-dev-stepfunctions-role"
```

## Lista de recursos creados

| Recurso | Nombre / Identificador | Región | Propósito |
|---|---|---|---|
| S3 Bucket | `finbank-bronze-dev-278714105600` | us-east-1 | Data Lake — capa Bronze (datos crudos) |
| S3 Bucket | `finbank-silver-dev-278714105600` | us-east-1 | Data Lake — capa Silver (datos limpios) |
| S3 Bucket | `finbank-gold-dev-278714105600` | us-east-1 | Data Lake — capa Gold (modelo dimensional) |
| S3 Bucket (bootstrap) | `finbank-tfstate-278714105600` | us-east-1 | Backend remoto del estado de Terraform |
| VPC Endpoint (Gateway) | `vpce-084b81bc7bd8a20bd` | us-east-1 | Acceso privado de Glue a S3 sin NAT Gateway |
| RDS PostgreSQL | `finbank-dev` (`db-J2SD532KQKAK7U6UDELUN7SDBE`) | us-east-1 | Base de datos origen (sistema transaccional FinBank) |
| DB Subnet Group | `finbank-dev-db-subnet-group` | us-east-1 | Subredes por defecto para RDS |
| Security Group | `finbank-dev-rds-sg` | us-east-1 | Firewall de RDS (solo Glue + IP autorizada) |
| Security Group | `finbank-dev-glue-sg` | us-east-1 | Firewall de las ENIs de la conexión Glue↔VPC |
| Secrets Manager | `finbank/dev/rds/credentials` | us-east-1 | Credenciales de RDS (generadas, nunca escritas a mano) |
| Glue Database | `finbank_dev_catalog` | us-east-1 | Catálogo de datos del proyecto |
| Glue Connection | `finbank-dev-rds-connection` | us-east-1 | Conexión JDBC de Glue Jobs hacia RDS |
| Glue Crawler ×3 | `finbank-dev-{bronze,silver,gold}-crawler` | us-east-1 | Sincroniza el catálogo con el esquema real de cada capa |
| IAM Role | `finbank-dev-glue-role` | global | Identidad de servicio de los Glue Jobs (Fase 3) |
| IAM Role | `finbank-dev-stepfunctions-role` | global | Identidad de servicio del orquestador (Fase 4) |
| SNS Topic | `finbank-dev-pipeline-alerts` | us-east-1 | Alertas operacionales del pipeline |
| DynamoDB (bootstrap) | `finbank-tfstate-lock` | us-east-1 | Lock del estado de Terraform |
| CloudWatch Log Group | `/aws-glue/jobs/finbank-dev` | us-east-1 | Logs de ejecución de Glue Jobs |
| CloudWatch Log Group | `/aws/vendedlogs/states/finbank-dev` | us-east-1 | Logs de Step Functions |
| CloudWatch Dashboard | `finbank-dev-pipeline` | us-east-1 | Monitoreo visual del pipeline |

## Evidencia de conectividad end-to-end (RDS real)

Con la infraestructura desplegada, se re-ejecutó `data-generation/load_to_postgres.py`
contra el endpoint real de RDS (antes solo se había probado contra un Postgres
local en Docker). Resultado:

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

Esto confirma: el Security Group de RDS permite la conexión desde la IP
autorizada, las credenciales generadas por Terraform en Secrets Manager son
válidas, y el esquema relacional de la Fase 1 es 100% compatible con el RDS
real (mismo `schema.sql` usado en ambas pruebas).

## Incidentes de seguridad durante el despliegue (y su resolución)

Documentados también en el CHANGELOG, por transparencia:

1. **Exposición accidental de un Access Key de AWS** en el chat de desarrollo.
   Resuelto: llave revocada y recreada de inmediato; nunca se usó para desplegar nada.
2. **Exposición accidental del password de RDS** al fallar un pipe de shell
   con comillas anidadas mal escapadas. Resuelto: password rotado vía
   `terraform apply -replace=random_password.db_password` (RDS + Secrets
   Manager actualizados atómicamente); se reemplazó el comando frágil por un
   script Python (`fetch_db_credentials.py`) sin ese riesgo.

## Pendiente antes de destruir la infraestructura

Por instrucción del candidato: **no se destruirá ningún recurso** hasta contar
con evidencia de una ejecución exitosa del pipeline completo (Fases 3 y 4).

## Nota sobre costos

Todos los recursos están dentro de la capa gratuita de AWS (S3, RDS
db.t3.micro/20GB, Glue Data Catalog, CloudWatch, SNS, DynamoDB
PAY_PER_REQUEST) **excepto** Secrets Manager, que tiene un periodo de prueba
de 30 días por secreto y luego ~USD 0.40/mes — sin impacto real dado el
alcance de 7 días hábiles de la prueba, siempre que los recursos se destruyan
al finalizar.
