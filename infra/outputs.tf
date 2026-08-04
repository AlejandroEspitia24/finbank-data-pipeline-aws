output "s3_bucket_names" {
  description = "Nombres de los buckets del Data Lake por capa Medallion."
  value       = { for k, b in aws_s3_bucket.medallion : k => b.bucket }
}

output "s3_bucket_arns" {
  description = "ARNs de los buckets del Data Lake por capa Medallion."
  value       = { for k, b in aws_s3_bucket.medallion : k => b.arn }
}

output "rds_endpoint" {
  description = "Endpoint (host:puerto) de la base de datos origen."
  value       = "${aws_db_instance.finbank.address}:${aws_db_instance.finbank.port}"
}

output "rds_secret_arn" {
  description = "ARN del secreto en Secrets Manager con las credenciales de RDS."
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "glue_database_name" {
  description = "Nombre de la base de datos del Glue Data Catalog."
  value       = aws_glue_catalog_database.finbank.name
}

output "glue_role_arn" {
  description = "ARN del rol de servicio usado por los Glue Jobs (Fase 3)."
  value       = aws_iam_role.glue_role.arn
}

output "step_functions_role_arn" {
  description = "ARN del rol de servicio usado por la state machine de Step Functions (Fase 4)."
  value       = aws_iam_role.step_functions_role.arn
}

output "sns_topic_arn" {
  description = "ARN del topic SNS de alertas del pipeline."
  value       = aws_sns_topic.pipeline_alerts.arn
}

output "cloudwatch_dashboard_url" {
  description = "URL directa al dashboard de monitoreo del pipeline."
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.pipeline.dashboard_name}"
}

output "state_machine_arn" {
  description = "ARN de la state machine de Step Functions que orquesta Bronze -> Silver -> Gold (Fase 4)."
  value       = aws_sfn_state_machine.pipeline.arn
}

output "scheduler_name" {
  description = "Nombre del schedule de EventBridge Scheduler que dispara el pipeline diariamente."
  value       = aws_scheduler_schedule.daily_pipeline_run.name
}

output "volume_anomaly_lambda_name" {
  description = "Nombre de la función Lambda que valida el volumen de ingesta Bronze contra los últimos 7 días."
  value       = aws_lambda_function.check_volume_anomaly.function_name
}

output "governance_role_arns" {
  description = "ARNs de los 3 roles IAM de gobierno de acceso humano (Fase 5)."
  value = {
    data_engineer = aws_iam_role.data_engineer.arn
    analyst       = aws_iam_role.analyst.arn
    administrator = aws_iam_role.administrator.arn
  }
}

output "cloudtrail_bucket_name" {
  description = "Bucket S3 donde CloudTrail entrega los logs de auditoría."
  value       = aws_s3_bucket.cloudtrail_logs.id
}

output "cloudtrail_arn" {
  description = "ARN del trail de CloudTrail."
  value       = aws_cloudtrail.main.arn
}
