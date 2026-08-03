output "state_bucket_name" {
  description = "Nombre del bucket S3 a usar como backend remoto en infra/backend.hcl"
  value       = aws_s3_bucket.tf_state.bucket
}

output "lock_table_name" {
  description = "Nombre de la tabla DynamoDB a usar como backend remoto en infra/backend.hcl"
  value       = aws_dynamodb_table.tf_lock.name
}
