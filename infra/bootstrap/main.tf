# Bootstrap: crea únicamente lo necesario para que el proyecto principal
# (../) pueda usar un backend remoto de estado en S3.
#
# Este módulo se aplica UNA sola vez, con estado local (no remoto — es el
# único lugar del proyecto donde eso es correcto, precisamente porque este
# es el módulo que crea el backend para todo lo demás). No se vuelve a tocar
# salvo que se destruya todo el proyecto al final de la prueba.

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

# Bucket S3 donde vivirá el terraform.tfstate del proyecto principal.
resource "aws_s3_bucket" "tf_state" {
  bucket = "${var.project_name}-tfstate-${data.aws_caller_identity.current.account_id}"

  # Protección extra: evita que un "terraform destroy" accidental en el
  # bootstrap se lleve por delante el estado de TODO el proyecto principal.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Tabla DynamoDB para el locking del estado: evita que dos "terraform apply"
# corran al mismo tiempo y corrompan el archivo de estado.
# PAY_PER_REQUEST: sin capacidad reservada que facture por hora inactiva —
# coherente con el criterio de costo cero en reposo del resto del proyecto.
resource "aws_dynamodb_table" "tf_lock" {
  name         = "${var.project_name}-tfstate-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

data "aws_caller_identity" "current" {}
