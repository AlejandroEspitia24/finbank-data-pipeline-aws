variable "project_name" {
  description = "Prefijo para nombrar todos los recursos del proyecto."
  type        = string
  default     = "finbank"
}

variable "environment" {
  description = "Entorno de despliegue: dev o prod (exigido por el enunciado, al menos 2 entornos soportados)."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment debe ser \"dev\" o \"prod\"."
  }
}

variable "aws_region" {
  description = "Región AWS de trabajo."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Perfil de AWS CLI local a usar (nunca credenciales en texto plano)."
  type        = string
  default     = "prueba-tecnica-finbank"
}

variable "db_name" {
  description = "Nombre de la base de datos PostgreSQL origen."
  type        = string
  default     = "finbank"
}

variable "db_username" {
  description = "Usuario administrador de RDS. La contraseña NUNCA se define aquí: se genera aleatoriamente y se guarda directo en Secrets Manager (ver secrets.tf)."
  type        = string
  default     = "finbank_admin"
}

variable "db_instance_class" {
  description = "Clase de instancia RDS. db.t3.micro está dentro de la capa gratuita (750h/mes durante 12 meses)."
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage_gb" {
  description = "Almacenamiento de RDS en GB. 20GB es el máximo cubierto por la capa gratuita."
  type        = number
  default     = 20
}

variable "allowed_ip_cidr" {
  description = <<-EOT
    CIDR (tu IP pública + /32) autorizado a conectarse a RDS directamente,
    para poder correr data-generation/load_to_postgres.py desde tu máquina.
    Obtener con: curl -s https://checkip.amazonaws.com
    Nunca usar 0.0.0.0/0 aquí — expondría la base de datos a todo internet.
  EOT
  type        = string
}

variable "alert_email" {
  description = "Correo que recibirá las alertas del pipeline (fallo, resumen diario, anomalías de volumen) vía SNS."
  type        = string
}

variable "glue_worker_type" {
  description = "Tipo de worker de Glue. G.1X es el más pequeño/económico disponible."
  type        = string
  default     = "G.1X"
}

variable "glue_number_of_workers" {
  description = "Número de workers de Glue por job. Mínimo permitido = 2."
  type        = number
  default     = 2
}

variable "log_retention_days" {
  description = "Días de retención de logs en CloudWatch (controla el costo de almacenamiento de logs)."
  type        = number
  default     = 14
}
