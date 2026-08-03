resource "aws_glue_catalog_database" "finbank" {
  name = "${var.project_name}_${var.environment}_catalog"
}

# Conexión de red que los Glue Jobs (Fase 3) usarán para llegar a RDS,
# corriendo dentro de la VPC con el Security Group dedicado.
resource "aws_glue_connection" "rds" {
  name            = "${var.project_name}-${var.environment}-rds-connection"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:postgresql://${aws_db_instance.finbank.address}:${aws_db_instance.finbank.port}/${var.db_name}"
    USERNAME            = var.db_username
    PASSWORD            = random_password.db_password.result
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.selected.availability_zone
    security_group_id_list = [aws_security_group.glue_connection.id]
    subnet_id              = data.aws_subnets.default.ids[0]
  }
}

# Un crawler por capa: mantiene el Glue Data Catalog sincronizado con el
# esquema real de los archivos Parquet en cada bucket, para que Athena /
# consultas analíticas puedan usarlas sin registrar tablas a mano.
resource "aws_glue_crawler" "medallion" {
  for_each      = aws_s3_bucket.medallion
  name          = "${var.project_name}-${var.environment}-${each.key}-crawler"
  role          = aws_iam_role.glue_role.arn
  database_name = aws_glue_catalog_database.finbank.name

  s3_target {
    path = "s3://${each.value.bucket}/"
  }

  # No se programa ejecución automática aquí: el propio pipeline
  # (Step Functions, Fase 4) dispara el crawler de Gold al finalizar cada
  # corrida exitosa, en vez de correr en un horario fijo independiente.
  schedule = null

  configuration = jsonencode({
    Version = 1.0
    Grouping = {
      TableGroupingPolicy = "CombineCompatibleSchemas"
    }
  })
}
