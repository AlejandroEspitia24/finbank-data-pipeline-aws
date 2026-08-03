# Data Lake: un bucket por capa Medallion, tal como exige el enunciado
# ("S3 Buckets separados para bronze, silver y gold"). Separarlos físicamente
# (no solo por prefijo dentro de un único bucket) permite aplicar políticas
# IAM y ciclos de vida distintos por capa — por ejemplo, el rol "Analista"
# de la Fase 5 solo podrá leer el bucket Gold.

locals {
  medallion_layers = ["bronze", "silver", "gold"]
}

resource "aws_s3_bucket" "medallion" {
  for_each = toset(local.medallion_layers)
  bucket   = "${var.project_name}-${each.key}-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "medallion" {
  for_each = aws_s3_bucket.medallion
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "medallion" {
  for_each = aws_s3_bucket.medallion
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "medallion" {
  for_each                = aws_s3_bucket.medallion
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Aborta uploads multiparte incompletos tras 7 días: evita pagar
# almacenamiento por fragmentos de cargas fallidas que nadie limpia a mano.
resource "aws_s3_bucket_lifecycle_configuration" "medallion" {
  for_each = aws_s3_bucket.medallion
  bucket   = each.value.id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"
    filter {} # Bloque vacío = la regla aplica a todos los objetos del bucket.
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# VPC Endpoint tipo "Gateway" para S3: gratuito, permite que Glue (corriendo
# con conexión a la VPC para llegar a RDS) llegue a S3 sin salir a internet
# y sin necesitar NAT Gateway.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.default.ids
}

data "aws_route_tables" "default" {
  vpc_id = data.aws_vpc.default.id
}
