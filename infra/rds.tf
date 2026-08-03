resource "aws_db_subnet_group" "finbank" {
  name       = "${var.project_name}-${var.environment}-db-subnet-group"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_security_group" "rds" {
  name        = "${var.project_name}-${var.environment}-rds-sg"
  description = "Acceso a PostgreSQL: solo desde Glue (VPC) y la IP autorizada del desarrollador."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Glue to PostgreSQL"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.glue_connection.id]
  }

  ingress {
    description = "Acceso administrativo puntual (carga inicial de datos, Fase 1)"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ip_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "finbank" {
  identifier     = "${var.project_name}-${var.environment}"
  engine         = "postgres"
  engine_version = "16"

  # db.t3.micro + 20GB gp2: dentro de la capa gratuita de RDS (750h/mes,
  # 20GB durante los primeros 12 meses). Nunca subir de tamaño sin revisar
  # el impacto en el crédito disponible.
  instance_class         = var.db_instance_class
  allocated_storage      = var.db_allocated_storage_gb
  storage_type           = "gp2"
  db_name                = var.db_name
  username               = var.db_username
  password               = random_password.db_password.result
  db_subnet_group_name   = aws_db_subnet_group.finbank.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # publicly_accessible=true es necesario para poder correr
  # load_to_postgres.py desde la máquina local durante el desarrollo; el
  # acceso real está restringido por el Security Group (IP + Glue), no por
  # exposición de red. En un entorno productivo real esto se movería a una
  # subred privada con acceso solo vía bastion/VPN.
  publicly_accessible = true

  multi_az                   = false # Multi-AZ duplica el costo; innecesario para datos sintéticos de prueba.
  backup_retention_period    = 1
  skip_final_snapshot        = true
  deletion_protection        = false # Debe poder destruirse limpio con "terraform destroy" al cerrar la prueba.
  auto_minor_version_upgrade = true
  apply_immediately          = true
}
