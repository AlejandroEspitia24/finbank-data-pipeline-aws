variable "project_name" {
  description = "Prefijo usado para nombrar todos los recursos del proyecto."
  type        = string
  default     = "finbank"
}

variable "aws_region" {
  description = "Región AWS de trabajo (recomendada por la guía de la prueba: us-east-1)."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Perfil de AWS CLI local a usar (nunca credenciales en texto plano)."
  type        = string
  default     = "prueba-tecnica-finbank"
}
