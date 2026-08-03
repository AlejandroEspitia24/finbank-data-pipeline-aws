data "aws_caller_identity" "current" {}

# Se usa la VPC y subredes por defecto de la cuenta (gratuitas, ya existen)
# en vez de crear una VPC propia. Justificación completa en el README de
# /infra: evita cualquier dependencia de NAT Gateway, que no está en la capa
# gratuita y cobra por hora incluso sin tráfico.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Subred específica usada por RDS y por la conexión VPC de Glue. Se necesita
# su Availability Zone explícita: sin ella, Glue no puede resolver dónde
# desplegar la ENI de la conexión ("Unable to resolve any valid connection").
data "aws_subnet" "selected" {
  id = data.aws_subnets.default.ids[0]
}
