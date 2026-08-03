# Infraestructura como Código — FinBank (AWS / Terraform)

## Prerrequisitos

- Terraform >= 1.9
- AWS CLI configurado con el perfil `prueba-tecnica-finbank` (`aws configure`, ver `docs/PLAN.md`)
- Usuario IAM con permisos suficientes para crear los recursos de este proyecto

## Paso 1 — Bootstrap (una sola vez)

Crea el bucket S3 y la tabla DynamoDB que usará el backend remoto del proyecto principal.

```bash
cd infra/bootstrap
terraform init
terraform apply -var="aws_profile=prueba-tecnica-finbank"
terraform output
```

Copia los valores de `state_bucket_name` y `lock_table_name` del output.

## Paso 2 — Configurar el backend remoto

```bash
cd ../
cp backend.hcl.example backend.hcl
# Editar backend.hcl con los valores reales del paso 1
```

## Paso 3 — Variables del entorno

```bash
cp dev.tfvars.example dev.tfvars
# Editar dev.tfvars: alert_email y allowed_ip_cidr (tu IP pública, ver comentario en el archivo)
```

## Paso 4 — Desplegar

```bash
terraform init -backend-config=backend.hcl
terraform plan -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars
```

## Paso 5 — Confirmar la suscripción SNS

AWS envía un correo a `alert_email` con un enlace de confirmación. **Las alertas no
funcionan hasta hacer clic en ese enlace.**

## Paso 6 — Cargar los datos generados en la Fase 1

Con `rds_endpoint` del output de Terraform, completa `data-generation/.env`
(a partir de `.env.example`) y corre `python load_to_postgres.py`.

## Destruir todo al terminar una sesión de trabajo

Para no dejar RDS ni otros recursos facturando sin supervisión:

```bash
terraform destroy -var-file=dev.tfvars
```

El bootstrap (`infra/bootstrap`) **no** se destruye entre sesiones — solo al
cerrar la prueba definitivamente, y solo después de haber destruido el
proyecto principal (el bootstrap sostiene su backend de estado).

## Por qué la VPC por defecto y no una VPC propia

Ver comentarios en `data.tf` y `s3.tf`. Resumen: evita cualquier dependencia
de NAT Gateway, que no está en la capa gratuita y cobra por hora aunque no
se use — el resto de la seguridad de red se resuelve con Security Groups
acotados (Glue y una única IP autorizada) en vez de aislamiento de subred.

## Recursos creados

| Recurso | Archivo | Propósito |
|---|---|---|
| S3 (bronze/silver/gold) | `s3.tf` | Data Lake |
| RDS PostgreSQL | `rds.tf` | Base de datos origen |
| Secrets Manager | `secrets.tf` | Credenciales de RDS (generadas, nunca escritas a mano) |
| Glue Database + Crawlers + Connection | `glue.tf` | Catálogo de datos y acceso JDBC a RDS |
| IAM (rol Glue, rol Step Functions) | `iam.tf` | Identidades de servicio de mínimo privilegio |
| SNS Topic | `sns.tf` | Alertas operacionales del pipeline |
| CloudWatch Log Groups + Dashboard | `cloudwatch.tf` | Monitoreo y retención de logs |
