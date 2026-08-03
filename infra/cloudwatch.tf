# Log groups explícitos (en vez de dejar que Glue/Step Functions los cree
# automáticamente con retención infinita) para controlar cuánto tiempo se
# guardan los logs y, con eso, el costo de almacenamiento en CloudWatch.
resource "aws_cloudwatch_log_group" "glue_jobs" {
  name              = "/aws-glue/jobs/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "step_functions" {
  name              = "/aws/vendedlogs/states/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days
}

# Dashboard mínimo de monitoreo del pipeline (Fase 4 lo exige: "estado de
# cada ejecución visible sin necesidad de acceder al código fuente").
resource "aws_cloudwatch_dashboard" "pipeline" {
  dashboard_name = "${var.project_name}-${var.environment}-pipeline"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "log"
        x      = 0
        y      = 0
        width  = 24
        height = 8
        properties = {
          title  = "Últimas ejecuciones del pipeline (Step Functions)"
          region = var.aws_region
          query  = "SOURCE '${aws_cloudwatch_log_group.step_functions.name}' | fields @timestamp, @message | sort @timestamp desc | limit 50"
        }
      }
    ]
  })
}
