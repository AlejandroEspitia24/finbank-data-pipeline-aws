# Fase 4 — Orquestación: Step Functions encadena Bronze -> validación de
# volumen (Lambda) -> Silver -> Gold, con reintentos y alertas SNS.
# EventBridge Scheduler dispara la ejecución diaria automática.

# ---------------------------------------------------------------------------
# Lambda: validación de volumen anómalo (informativa, no bloqueante)
# ---------------------------------------------------------------------------

data "archive_file" "check_volume_anomaly" {
  type        = "zip"
  source_file = "${path.module}/../orchestration/lambda/check_volume_anomaly.py"
  output_path = "${path.module}/../orchestration/lambda/check_volume_anomaly.zip"
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_volume_anomaly" {
  name               = "${var.project_name}-${var.environment}-volume-anomaly-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "lambda_volume_anomaly_custom" {
  statement {
    sid       = "ReadBronzeIngestionLogs"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.medallion["bronze"].arn, "${aws_s3_bucket.medallion["bronze"].arn}/*"]
  }

  statement {
    sid       = "PublishVolumeAlerts"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.pipeline_alerts.arn]
  }

  statement {
    sid       = "LambdaLogs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.environment}-*"]
  }
}

resource "aws_iam_role_policy" "lambda_volume_anomaly_custom" {
  name   = "${var.project_name}-${var.environment}-volume-anomaly-policy"
  role   = aws_iam_role.lambda_volume_anomaly.id
  policy = data.aws_iam_policy_document.lambda_volume_anomaly_custom.json
}

resource "aws_cloudwatch_log_group" "lambda_volume_anomaly" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-volume-anomaly"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "check_volume_anomaly" {
  function_name    = "${var.project_name}-${var.environment}-volume-anomaly"
  role             = aws_iam_role.lambda_volume_anomaly.arn
  handler          = "check_volume_anomaly.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 128 # Solo lista/lee JSON pequeños en S3, no necesita más.
  filename         = data.archive_file.check_volume_anomaly.output_path
  source_code_hash = data.archive_file.check_volume_anomaly.output_base64sha256

  environment {
    variables = {
      BRONZE_BUCKET                = aws_s3_bucket.medallion["bronze"].bucket
      SNS_TOPIC_ARN                = aws_sns_topic.pipeline_alerts.arn
      VOLUME_ANOMALY_THRESHOLD_PCT = tostring(var.volume_anomaly_threshold_pct)
      VOLUME_ANOMALY_LOOKBACK_DAYS = "7"
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda_volume_anomaly]
}

# ---------------------------------------------------------------------------
# Lambda: resumen de la ejecución exitosa (registros por capa, tiempo total,
# alertas/rechazos de calidad) — el enunciado exige que el reporte diario de
# éxito incluya estos datos, no un mensaje genérico de "todo salió bien".
# ---------------------------------------------------------------------------

data "archive_file" "build_execution_summary" {
  type        = "zip"
  source_file = "${path.module}/../orchestration/lambda/build_execution_summary.py"
  output_path = "${path.module}/../orchestration/lambda/build_execution_summary.zip"
}

resource "aws_iam_role" "lambda_execution_summary" {
  name               = "${var.project_name}-${var.environment}-execution-summary-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "lambda_execution_summary_custom" {
  statement {
    sid     = "ReadAllLayerControlData"
    actions = ["s3:GetObject", "s3:ListBucket"]
    resources = flatten([
      for b in aws_s3_bucket.medallion : [b.arn, "${b.arn}/*"]
    ])
  }

  statement {
    sid       = "LambdaLogs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.environment}-*"]
  }
}

resource "aws_iam_role_policy" "lambda_execution_summary_custom" {
  name   = "${var.project_name}-${var.environment}-execution-summary-policy"
  role   = aws_iam_role.lambda_execution_summary.id
  policy = data.aws_iam_policy_document.lambda_execution_summary_custom.json
}

resource "aws_cloudwatch_log_group" "lambda_execution_summary" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-execution-summary"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "build_execution_summary" {
  function_name    = "${var.project_name}-${var.environment}-execution-summary"
  role             = aws_iam_role.lambda_execution_summary.arn
  handler          = "build_execution_summary.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 128
  filename         = data.archive_file.build_execution_summary.output_path
  source_code_hash = data.archive_file.build_execution_summary.output_base64sha256

  environment {
    variables = {
      BRONZE_BUCKET = aws_s3_bucket.medallion["bronze"].bucket
      SILVER_BUCKET = aws_s3_bucket.medallion["silver"].bucket
      GOLD_BUCKET   = aws_s3_bucket.medallion["gold"].bucket
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda_execution_summary]
}

# ---------------------------------------------------------------------------
# Step Functions: state machine que encadena los 3 Glue Jobs
# ---------------------------------------------------------------------------

resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.project_name}-${var.environment}-pipeline"
  role_arn = aws_iam_role.step_functions_role.arn
  type     = "STANDARD" # Ejecución diaria (no alto volumen de invocaciones) -> Standard es más barato que Express en este caso.

  definition = templatefile("${path.module}/../orchestration/state_machine.asl.json.tftpl", {
    bronze_job_name    = aws_glue_job.bronze.name
    silver_job_name    = aws_glue_job.silver.name
    gold_job_name      = aws_glue_job.gold.name
    volume_lambda_arn  = aws_lambda_function.check_volume_anomaly.arn
    summary_lambda_arn = aws_lambda_function.build_execution_summary.arn
    sns_topic_arn      = aws_sns_topic.pipeline_alerts.arn
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.step_functions.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }
}

# ---------------------------------------------------------------------------
# EventBridge Scheduler: ejecución diaria automática del pipeline
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler_role" {
  name               = "${var.project_name}-${var.environment}-scheduler-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json
}

data "aws_iam_policy_document" "scheduler_custom" {
  statement {
    sid       = "StartPipelineExecution"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.pipeline.arn]
  }
}

resource "aws_iam_role_policy" "scheduler_custom" {
  name   = "${var.project_name}-${var.environment}-scheduler-policy"
  role   = aws_iam_role.scheduler_role.id
  policy = data.aws_iam_policy_document.scheduler_custom.json
}

resource "aws_scheduler_schedule" "daily_pipeline_run" {
  name       = "${var.project_name}-${var.environment}-daily-run"
  group_name = "default"

  # Pausado deliberadamente (state = "DISABLED") mientras se espera la
  # sustentación: evita que el pipeline siga corriendo (y generando costo
  # de Glue) todos los días sin nadie revisando los resultados. La
  # infraestructura completa sigue desplegada — una ejecución manual
  # (`aws stepfunctions start-execution`) sigue funcionando en segundos
  # para una demo en vivo. Reactivar: cambiar a "ENABLED" y aplicar.
  state = var.pipeline_schedule_enabled ? "ENABLED" : "DISABLED"

  schedule_expression          = var.pipeline_schedule_expression
  schedule_expression_timezone = var.pipeline_schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.pipeline.arn
    role_arn = aws_iam_role.scheduler_role.arn
  }
}
