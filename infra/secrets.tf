# La contraseña de RDS nunca la escribe una persona: Terraform la genera
# aleatoriamente y la entrega directo a Secrets Manager. Ningún humano llega
# a verla ni a copiarla — elimina la posibilidad de que termine pegada en un
# chat, un .tfvars o un commit por error.
resource "random_password" "db_password" {
  length  = 32
  special = true
  # Excluye caracteres que suelen dar problemas dentro de connection strings
  # JDBC/URL (usados por Glue y por load_to_postgres.py).
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "${var.project_name}/${var.environment}/rds/credentials"
  description = "Credenciales de conexión a la base de datos origen PostgreSQL de FinBank."
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db_password.result
    host     = aws_db_instance.finbank.address
    port     = aws_db_instance.finbank.port
    dbname   = var.db_name
  })
}
