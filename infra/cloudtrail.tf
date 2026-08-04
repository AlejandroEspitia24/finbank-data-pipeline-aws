# Fase 5 — Auditoría de accesos: CloudTrail registra quién hizo qué,
# cuándo y desde dónde, sobre toda la cuenta (incluyendo qué rol de
# gobierno asumió cada quién — ver iam_governance.tf).
#
# Alcance: trail de una sola región (no multi-región, todo el proyecto
# vive en us-east-1) con eventos de administración (management events,
# gratis: la primera copia entregada a un trail por región no tiene costo
# de CloudTrail en sí) MÁS eventos de datos (data events) a nivel de
# objeto, pero acotados solo a los 3 buckets del Data Lake
# (bronze/silver/gold) — no a "todo S3 de la cuenta".
#
# Corrección tras auditoría: la Fase 5 exige explícitamente que el sistema
# pueda responder "¿quién accedió a qué dato y en qué momento?". Los
# management events (quién creó/modificó un recurso) NO responden esa
# pregunta — para eso se necesitan específicamente los data events de S3
# (cada GetObject/PutObject individual). Sí tienen costo por evento
# (~USD 0.10 por 100.000 eventos en us-east-1), pero acotarlos a los 3
# buckets del Data Lake (en vez de "todos los buckets de la cuenta",
# que incluiría también el bucket de logs de Terraform y el de
# CloudTrail) mantiene el volumen y el costo bajo control mientras se
# cumple el requisito real de auditoría a nivel de dato.

resource "aws_s3_bucket" "cloudtrail_logs" {
  bucket = "${var.project_name}-cloudtrail-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "cloudtrail_logs" {
  bucket                  = aws_s3_bucket.cloudtrail_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Los logs de auditoría no necesitan guardarse para siempre en una cuenta
# de prueba: 90 días es suficiente para demostrar el mecanismo y controla
# el costo de almacenamiento indefinidamente creciente.
resource "aws_s3_bucket_lifecycle_configuration" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id
  rule {
    id     = "expire-after-90-days"
    status = "Enabled"
    filter {}
    expiration {
      days = 90
    }
  }
}

data "aws_iam_policy_document" "cloudtrail_bucket_policy" {
  statement {
    sid       = "AWSCloudTrailAclCheck"
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.cloudtrail_logs.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }

  statement {
    sid       = "AWSCloudTrailWrite"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.cloudtrail_logs.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id
  policy = data.aws_iam_policy_document.cloudtrail_bucket_policy.json
}

resource "aws_cloudtrail" "main" {
  name                          = "${var.project_name}-${var.environment}-trail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail_logs.id
  is_multi_region_trail         = false
  include_global_service_events = true
  enable_log_file_validation    = true

  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type   = "AWS::S3::Object"
      values = [for b in aws_s3_bucket.medallion : "${b.arn}/"]
    }
  }

  depends_on = [aws_s3_bucket_policy.cloudtrail_logs]
}
