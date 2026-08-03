# Changelog

Todas las entradas relevantes del desarrollo de la prueba técnica se registran aquí.

## [Sin publicar]

### 2026-08-02
- Repositorio inicializado.
- Documentos de la prueba técnica cargados y analizados (`docs/`).
- Decisiones iniciales tomadas: escenario A (FinBank/Banca), plataforma AWS, Terraform, AWS Glue (PySpark), AWS Step Functions.
- Plan de proyecto completo documentado en `docs/PLAN.md`.
- Estructura de carpetas del repositorio creada (`/infra`, `/data-generation`, `/pipelines`, `/orchestration`, `/docs`).
- **Fase 1 completada:** script de generación de datos sintéticos de FinBank (`data-generation/generate_data.py`) con semilla fija, integridad referencial, ~5% de nulos controlados y 3 anomalías intencionales documentadas.
- Esquema relacional origen (`data-generation/schema.sql`) y script de carga a PostgreSQL (`data-generation/load_to_postgres.py`), validados localmente contra PostgreSQL 16 en Docker.
- Diagrama Entidad-Relación (`docs/er-diagram.md`) y evidencia de carga (`docs/evidencia-fase1-carga.md`).
- **Fase 2 completada:** infraestructura AWS desplegada vía Terraform (`/infra`) — 3 buckets S3 (bronze/silver/gold), RDS PostgreSQL, Glue Database + Crawlers + Connection, roles IAM de servicio (Glue, Step Functions), Secrets Manager, SNS, CloudWatch (log groups + dashboard), VPC Endpoint de S3. Backend remoto de estado en S3 + DynamoDB (`/infra/bootstrap`).
- Datos sintéticos de la Fase 1 cargados exitosamente en el RDS real (6.780.750 registros verificados). Evidencia completa en `docs/evidencia-fase2-infra.md`.
- **Incidente de seguridad (Access Key de AWS):** una llave de acceso se expuso accidentalmente en el chat de desarrollo. Revocada y recreada de inmediato; nunca se usó para desplegar infraestructura.
- **Incidente de seguridad (password de RDS):** el password se expuso accidentalmente por un fallo de escapado de comillas en un comando de terminal. Rotado de inmediato vía `terraform apply -replace=random_password.db_password`.
- **Fase 3 (Bronze) completada:** Glue Job `finbank-dev-bronze-ingest` (`pipelines/bronze/bronze_ingest.py`) ingesta las 6 tablas desde RDS a S3 en Parquet, con metadatos de auditoría, particionado por fecha de ingesta, modo incremental (watermark por tabla) y log de ejecución. Utilidades compartidas en `pipelines/common/glue_utils.py`. Definición del job en `infra/glue_jobs.tf`.
- Corregidos 3 bugs encontrados al ejecutar el job contra AWS real: falta de `availability_zone` en la conexión Glue↔VPC, y URL JDBC incompleta devuelta por `extract_jdbc_conf()` (sin prefijo `jdbc:` y sin nombre de base de datos). Evidencia completa y detalle de cada fallo en `docs/evidencia-fase3-bronze.md`.
- **Fase 3 (Silver) completada:** Glue Job `finbank-dev-silver-clean` (`pipelines/silver/silver_clean.py`) — deduplicación, validación de integridad referencial (tabla de errores unificada), enmascaramiento/hash de PII (SHA-256), imputación de nulos documentada por columna, cálculo de `ind_sospechoso` (ventana de 30 días por cliente), reporte de calidad de datos y 5 verificaciones automatizadas (10/10 PASSED).
- **Fase 3 (Gold) completada:** Glue Job `finbank-dev-gold-transform` (`pipelines/gold/gold_transform.py`) — modelo dimensional completo (4 dimensiones, 3 hechos, 1 tabla de KPIs), reglas de negocio de FinBank (`bucket_mora`, provisión estimada, CLTV 12 meses), linaje documentado de 5 campos calculados en `pipelines/gold/README.md`.
- Pipeline Bronze → Silver → Gold verificado de extremo a extremo contra AWS real, con trazabilidad de conteos consistente en las tres capas. Evidencia completa en `docs/evidencia-fase3-silver-gold.md`, incluyendo un hallazgo documentado (no oculto) sobre la tasa de falsos positivos de `ind_sospechoso` con ventanas pequeñas por cliente.
- **Gap de control de costos detectado y corregido:** no existía ningún AWS Budget en la cuenta (el paso manual de consola planeado en la Fase 2 nunca se completó). Agregado como código Terraform (`infra/budget.tf`): USD 10/mes con alertas al 50%, 80% y 100% por correo. Verificado con `aws budgets describe-budgets`.
