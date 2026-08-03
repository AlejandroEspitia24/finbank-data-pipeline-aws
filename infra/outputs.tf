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
