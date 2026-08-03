terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Backend remoto: el bloque queda intencionalmente vacío aquí porque
  # Terraform NO permite usar variables dentro de un bloque "backend".
  # Los valores reales (bucket, tabla de lock, región) se pasan en tiempo
  # de "terraform init" con:
  #   terraform init -backend-config=backend.hcl
  # donde backend.hcl se genera a partir de los outputs de infra/bootstrap
  # y NUNCA se versiona (ver .gitignore). backend.hcl.example documenta el
  # formato esperado.
  backend "s3" {}
}
