# Evidencia — Fase 3 / Capa Bronze

## Resultado final (4º intento, tras 3 bugs corregidos en el camino)

| Tabla | Estado | Registros | Duración | Tamaño |
|---|---|---|---|---|
| tb_clientes_core | SUCCESS | 10.000 | 1.83s | 277.6 KB |
| tb_productos_cat | SUCCESS | 50 | 39.65s* | 5.2 KB |
| tb_sucursales_red | SUCCESS | 200 | 1.44s | 8.3 KB |
| tb_mov_financieros | SUCCESS | 501.500 | 11.67s | 16.38 MB |
| tb_obligaciones | SUCCESS | 30.000 | 1.98s | 1.09 MB |
| tb_comisiones_log | SUCCESS | 80.000 | 2.02s | 1.10 MB |

\* incluye el arranque en frío del clúster Spark (primera tabla procesada).

Los conteos coinciden exactamente con los cargados a RDS en la Fase 1/2,
incluyendo los 1.500 duplicados intencionales de `tb_mov_financieros`
(501.500 = 500.000 + 1.500 de la anomalía documentada).

Watermarks guardados correctamente para las 3 tablas incrementales
(`tb_mov_financieros`, `tb_obligaciones`, `tb_comisiones_log`) en
`_control/watermarks/`. Particionamiento por fecha de ingesta confirmado:
`tb_mov_financieros/anio=2026/mes=08/dia=03/`.

## Bugs reales encontrados y resueltos (3 intentos fallidos antes del éxito)

Este es el tipo de proceso de depuración iterativa que vale la pena
documentar para la sustentación — nada funcionó al primer intento, y cada
fallo aisló un problema distinto:

**Intento 1 — `Unable to resolve any valid connection` (fallo a nivel de
job, ni siquiera llegó a correr el script Python).**
Causa: el bloque `physical_connection_requirements` de `aws_glue_connection`
no tenía `availability_zone`. Sin ese dato, Glue no puede resolver dónde
desplegar la ENI de la conexión VPC. Se había quitado por error al corregir
un bug anterior de sintaxis (una expresión que siempre evaluaba a `null`).
Fix: agregar `data "aws_subnet" "selected"` para obtener la AZ real de la
subred y pasarla explícitamente.

**Intento 2 — `PSQLException: Unable to parse URL` (el job corrió, pero las
6 tablas fallaron dentro de su propio try/except).**
Causa: `glue_context.extract_jdbc_conf()` no garantiza devolver la URL con el
prefijo `jdbc:` que el driver de PostgreSQL exige literalmente. Fix
defensivo: verificar y anteponer el prefijo si falta.

**Intento 3 — mismo error, `PSQLException: Unable to parse URL` (el fix
anterior era necesario pero no suficiente).**
Causa real, confirmada leyendo el log de CloudWatch línea por línea:
`extract_jdbc_conf()` también recorta el nombre de la base de datos de la
URL — devuelve solo `host:puerto`, no `host:puerto/basededatos`. El driver
de PostgreSQL directamente advierte `JDBC URL must contain a / at the end of
the host or port`. Fix: construir el sufijo `/db_name` nosotros mismos,
usando un parámetro del job (`--db_name`) en vez de confiar en el formato
exacto que devuelve la función de Glue.

**Lección de fondo:** `terraform validate` y `terraform plan` solo verifican
sintaxis y consistencia de referencias — nunca detectan estos tres bugs,
porque son errores de comportamiento en tiempo de ejecución dentro del motor
de Glue/Spark. La única forma de encontrarlos fue ejecutar el job de verdad
contra la infraestructura real y leer los logs de CloudWatch con atención.

## Costo real incurrido

4 ejecuciones del Glue Job (`G.1X × 2 workers`), duración total ~3.5 minutos
sumadas. Costo aproximado: **menos de USD 0.20** del crédito de prueba de
USD 300.
