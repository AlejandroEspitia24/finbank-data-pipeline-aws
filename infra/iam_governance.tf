# Fase 5 — Gobierno de acceso humano: 3 roles IAM que representan los
# perfiles que el enunciado exige (Ingeniero de Datos, Analista, Administrador).
#
# Decisión de diseño importante: son ROLES asumibles, no usuarios IAM
# nuevos. En una cuenta de equipo real, cada persona tendría su propio
# usuario/identidad (o federación vía IAM Identity Center) y se le
# asignaría el rol correspondiente a su función. Esta es una cuenta
# personal de prueba con un solo operador humano (finbank-terraform-
# deployer); crear 3 usuarios adicionales solo para "tener 3 personas"
# sería teatro, no gobierno real. Lo que sí se demuestra aquí es el
# principio en sí: los permisos existen por ROL/FUNCIÓN, separados unos de
# otros, no como un único usuario con acceso total a todo. El mismo
# principal puede assumir cualquiera de los 3 roles (ver política de
# confianza), pero cada sesión asumida queda acotada a los permisos de
# ESE rol específico mientras dure esa sesión — y auditable en CloudTrail
# (¿quién asumió qué rol y cuándo?).

data "aws_iam_policy_document" "assumable_by_deployer" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = [data.aws_caller_identity.current.arn]
    }
  }
}

# ---------------------------------------------------------------------------
# Ingeniero de Datos: lectura/escritura en las 3 capas del Data Lake +
# operación del pipeline (Glue, Step Functions), sin permisos de IAM.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "data_engineer" {
  name                 = "${var.project_name}-${var.environment}-data-engineer-role"
  assume_role_policy   = data.aws_iam_policy_document.assumable_by_deployer.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "data_engineer_policy" {
  statement {
    sid     = "ReadWriteAllLayers"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = flatten([
      for b in aws_s3_bucket.medallion : [b.arn, "${b.arn}/*"]
    ])
  }

  statement {
    sid       = "OperatePipeline"
    actions   = ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:GetJob", "glue:GetJobs", "glue:BatchStopJobRun"]
    resources = ["arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:job/${var.project_name}-*"]
  }

  statement {
    sid       = "ReadGlueCatalog"
    actions   = ["glue:GetDatabase", "glue:GetDatabases", "glue:GetTable", "glue:GetTables", "glue:GetPartitions"]
    resources = ["*"] # El catálogo de Glue no admite scoping fino por prefijo de nombre para estas acciones de lectura.
  }

  statement {
    sid       = "InspectPipelineExecutions"
    actions   = ["states:DescribeExecution", "states:ListExecutions", "states:GetExecutionHistory", "states:DescribeStateMachine"]
    resources = [aws_sfn_state_machine.pipeline.arn, "${aws_sfn_state_machine.pipeline.arn}*"]
  }

  statement {
    sid       = "ReadPipelineLogs"
    actions   = ["logs:GetLogEvents", "logs:FilterLogEvents", "logs:DescribeLogStreams", "logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:*"]
  }
}

resource "aws_iam_role_policy" "data_engineer_policy" {
  name   = "${var.project_name}-${var.environment}-data-engineer-policy"
  role   = aws_iam_role.data_engineer.id
  policy = data.aws_iam_policy_document.data_engineer_policy.json
}

# ---------------------------------------------------------------------------
# Analista: solo lectura sobre la capa Gold. Nunca ve Silver ni Bronze —
# nunca ve un dato crudo ni un hash de PII, solo el modelo dimensional
# final ya curado.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "analyst" {
  name                 = "${var.project_name}-${var.environment}-analyst-role"
  assume_role_policy   = data.aws_iam_policy_document.assumable_by_deployer.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "analyst_policy" {
  statement {
    sid       = "ReadOnlyGold"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.medallion["gold"].arn, "${aws_s3_bucket.medallion["gold"].arn}/*"]
  }

  statement {
    sid       = "ReadGoldCatalog"
    actions   = ["glue:GetDatabase", "glue:GetTable", "glue:GetTables", "glue:GetPartitions"]
    resources = ["*"] # Lectura de metadatos del catálogo; sin esto, Athena no puede resolver el esquema de las tablas Gold.
  }
}

resource "aws_iam_role_policy" "analyst_policy" {
  name   = "${var.project_name}-${var.environment}-analyst-policy"
  role   = aws_iam_role.analyst.id
  policy = data.aws_iam_policy_document.analyst_policy.json
}

# ---------------------------------------------------------------------------
# Administrador: control total. Se modela como el acceso ya existente del
# usuario deployer (AdministratorAccess) — este rol existe para que, en un
# escenario de equipo real, un administrador humano lo asuma temporalmente
# en vez de tener una identidad con AdministratorAccess de forma permanente
# y siempre activa.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "administrator" {
  name                 = "${var.project_name}-${var.environment}-administrator-role"
  assume_role_policy   = data.aws_iam_policy_document.assumable_by_deployer.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "administrator_policy" {
  role       = aws_iam_role.administrator.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
