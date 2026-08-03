# Security Group dedicado a las ENIs que Glue crea dentro de la VPC cuando
# usa una conexión de red (necesaria para llegar a RDS). Se autoreferencia
# porque Spark, dentro de un mismo job, necesita que sus propios workers se
# comuniquen entre sí.
resource "aws_security_group" "glue_connection" {
  name        = "${var.project_name}-${var.environment}-glue-sg"
  description = "ENIs de la conexion VPC de Glue hacia RDS."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Comunicacion interna entre workers de un mismo job Spark"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --------------------------------------------------------------------------- #
# Rol de servicio de AWS Glue — usado por todos los Glue Jobs (Bronze, Silver
# y Gold) definidos en la Fase 3.
# --------------------------------------------------------------------------- #

data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_role" {
  name               = "${var.project_name}-${var.environment}-glue-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
}

# Política administrada oficial de AWS con los permisos base que todo Glue
# Job necesita (logs, catálogo, métricas). Se complementa abajo con una
# política propia, acotada solo a los recursos de este proyecto.
resource "aws_iam_role_policy_attachment" "glue_service_role" {
  role       = aws_iam_role.glue_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_custom" {
  statement {
    sid     = "S3DataLakeAccess"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = flatten([
      for b in aws_s3_bucket.medallion : [b.arn, "${b.arn}/*"]
    ])
  }

  statement {
    sid       = "ReadDbCredentials"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db_credentials.arn]
  }

  statement {
    sid       = "PublishPipelineAlerts"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.pipeline_alerts.arn]
  }
}

resource "aws_iam_role_policy" "glue_custom" {
  name   = "${var.project_name}-${var.environment}-glue-custom-policy"
  role   = aws_iam_role.glue_role.id
  policy = data.aws_iam_policy_document.glue_custom.json
}

# --------------------------------------------------------------------------- #
# Rol de servicio de Step Functions — orquesta los Glue Jobs (Fase 4).
# --------------------------------------------------------------------------- #

data "aws_iam_policy_document" "step_functions_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "step_functions_role" {
  name               = "${var.project_name}-${var.environment}-stepfunctions-role"
  assume_role_policy = data.aws_iam_policy_document.step_functions_assume_role.json
}

data "aws_iam_policy_document" "step_functions_custom" {
  statement {
    sid = "RunAndMonitorGlueJobs"
    actions = [
      "glue:StartJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns",
      "glue:BatchStopJobRun",
    ]
    # Los Glue Jobs se crean en la Fase 3; se restringe por prefijo de
    # nombre (todos los jobs de este proyecto comparten prefijo) en vez de "*".
    resources = ["arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:job/${var.project_name}-*"]
  }

  statement {
    sid       = "PublishPipelineAlerts"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.pipeline_alerts.arn]
  }

  statement {
    sid = "StepFunctionsLogging"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"] # Estas acciones de CloudWatch Logs no admiten scoping por ARN de recurso específico.
  }
}

resource "aws_iam_role_policy" "step_functions_custom" {
  name   = "${var.project_name}-${var.environment}-stepfunctions-custom-policy"
  role   = aws_iam_role.step_functions_role.id
  policy = data.aws_iam_policy_document.step_functions_custom.json
}
