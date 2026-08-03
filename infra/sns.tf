resource "aws_sns_topic" "pipeline_alerts" {
  name = "${var.project_name}-${var.environment}-pipeline-alerts"
}

resource "aws_sns_topic_subscription" "email_alert" {
  topic_arn = aws_sns_topic.pipeline_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email

  # AWS envía un correo de confirmación a "endpoint" tras el apply. La
  # suscripción queda en estado "PendingConfirmation" hasta que se hace clic
  # en ese enlace — es un paso manual que Terraform no puede completar por
  # nosotros. Ver infra/README.md para el recordatorio en el flujo de
  # despliegue.
}
