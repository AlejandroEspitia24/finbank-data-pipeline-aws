# Scripts de los Glue Jobs: se suben al bucket Bronze bajo el prefijo
# "_scripts/", separado de los datos reales (prefijos con "_" quedan fuera
# del scope de los Crawlers, que solo escanean las carpetas de tablas).
# Se reutiliza el bucket Bronze como repositorio de scripts para las 3 capas
# — no se justifica un bucket adicional solo para código.

resource "aws_s3_object" "glue_common_utils" {
  bucket = aws_s3_bucket.medallion["bronze"].id
  key    = "_scripts/common/glue_utils.py"
  source = "${path.module}/../pipelines/common/glue_utils.py"
  etag   = filemd5("${path.module}/../pipelines/common/glue_utils.py")
}

resource "aws_s3_object" "glue_table_config" {
  bucket = aws_s3_bucket.medallion["bronze"].id
  key    = "_scripts/common/table_config.py"
  source = "${path.module}/../pipelines/common/table_config.py"
  etag   = filemd5("${path.module}/../pipelines/common/table_config.py")
}

resource "aws_s3_object" "bronze_script" {
  bucket = aws_s3_bucket.medallion["bronze"].id
  key    = "_scripts/bronze_ingest.py"
  source = "${path.module}/../pipelines/bronze/bronze_ingest.py"
  etag   = filemd5("${path.module}/../pipelines/bronze/bronze_ingest.py")
}

resource "aws_s3_object" "silver_script" {
  bucket = aws_s3_bucket.medallion["bronze"].id
  key    = "_scripts/silver_clean.py"
  source = "${path.module}/../pipelines/silver/silver_clean.py"
  etag   = filemd5("${path.module}/../pipelines/silver/silver_clean.py")
}

resource "aws_s3_object" "gold_script" {
  bucket = aws_s3_bucket.medallion["bronze"].id
  key    = "_scripts/gold_transform.py"
  source = "${path.module}/../pipelines/gold/gold_transform.py"
  etag   = filemd5("${path.module}/../pipelines/gold/gold_transform.py")
}

locals {
  common_py_files = join(",", [
    "s3://${aws_s3_bucket.medallion["bronze"].bucket}/${aws_s3_object.glue_common_utils.key}",
    "s3://${aws_s3_bucket.medallion["bronze"].bucket}/${aws_s3_object.glue_table_config.key}",
  ])
}

resource "aws_glue_job" "bronze" {
  name         = "${var.project_name}-${var.environment}-bronze-ingest"
  role_arn     = aws_iam_role.glue_role.arn
  glue_version = "4.0"

  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 30 # minutos

  # Sin reintentos propios de Glue: los reintentos con backoff exponencial
  # se gestionan centralizadamente desde Step Functions (Fase 4), no aquí,
  # para no duplicar la lógica de reintentos en dos capas distintas.
  max_retries = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.medallion["bronze"].bucket}/${aws_s3_object.bronze_script.key}"
    python_version  = "3"
  }

  connections = [aws_glue_connection.rds.name]

  default_arguments = {
    "--job-language"                     = "python"
    "--extra-py-files"                   = local.common_py_files
    "--rds_connection_name"              = aws_glue_connection.rds.name
    "--bronze_bucket"                    = aws_s3_bucket.medallion["bronze"].bucket
    "--db_name"                          = var.db_name
    "--TempDir"                          = "s3://${aws_s3_bucket.medallion["bronze"].bucket}/_tmp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--enable-job-insights"              = "false" # evita costo adicional de Job Insights en cuenta de prueba
  }
}

resource "aws_glue_job" "silver" {
  name         = "${var.project_name}-${var.environment}-silver-clean"
  role_arn     = aws_iam_role.glue_role.arn
  glue_version = "4.0"

  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 30

  max_retries = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.medallion["bronze"].bucket}/${aws_s3_object.silver_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--extra-py-files"                   = local.common_py_files
    "--bronze_bucket"                    = aws_s3_bucket.medallion["bronze"].bucket
    "--silver_bucket"                    = aws_s3_bucket.medallion["silver"].bucket
    "--TempDir"                          = "s3://${aws_s3_bucket.medallion["bronze"].bucket}/_tmp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--enable-job-insights"              = "false"
  }
}

resource "aws_glue_job" "gold" {
  name         = "${var.project_name}-${var.environment}-gold-transform"
  role_arn     = aws_iam_role.glue_role.arn
  glue_version = "4.0"

  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 30

  max_retries = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.medallion["bronze"].bucket}/${aws_s3_object.gold_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--extra-py-files"                   = local.common_py_files
    "--silver_bucket"                    = aws_s3_bucket.medallion["silver"].bucket
    "--gold_bucket"                      = aws_s3_bucket.medallion["gold"].bucket
    "--TempDir"                          = "s3://${aws_s3_bucket.medallion["bronze"].bucket}/_tmp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--enable-job-insights"              = "false"
  }
}
