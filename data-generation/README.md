# Fase 1 — Generación de datos y modelo relacional (FinBank)

## Archivos

| Archivo | Propósito |
|---|---|
| `config.yaml` | Parámetros de generación: semilla, volúmenes, rango de fechas, tasas de nulos/anomalías |
| `schema.sql` | DDL del esquema origen (6 tablas del sistema legado de FinBank) |
| `generate_data.py` | Genera los datos sintéticos y los guarda en `output/` (CSV + Parquet) |
| `load_to_postgres.py` | Aplica `schema.sql` y carga `output/*.parquet` a PostgreSQL |
| `logging_config.py` | Configuración de logging compartida (consola + archivo) |
| `.env.example` | Plantilla de variables de conexión a la base de datos (copiar a `.env`, nunca subir `.env`) |

## Cómo ejecutar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 1. Generar los datos sintéticos
python generate_data.py --config config.yaml

# 2. Cargar a PostgreSQL (completar .env primero, ver .env.example)
cp .env.example .env   # y editar con el endpoint real de RDS
python load_to_postgres.py
```

## Notas

- **Reproducibilidad:** toda la generación usa `numpy.random.default_rng(seed)`
  con la semilla definida en `config.yaml`. Correr el script dos veces con la
  misma semilla produce exactamente los mismos datos.
- **Compatibilidad de dependencias:** `requirements.txt` usa versiones mínimas
  (`>=`) en vez de pines exactos porque este entorno corre Python 3.14, muy
  reciente; pines antiguos exactos no tienen wheel precompilado para esa
  versión y fuerzan una compilación desde código fuente que falla. Si se
  necesita reproducir el build exacto probado, ver las versiones resueltas en
  `docs/evidencia-fase1-carga.md`.
- **Prueba local antes de AWS:** `load_to_postgres.py` fue validado contra un
  PostgreSQL 16 corriendo en Docker (mismo motor que usará Amazon RDS) antes
  de depender de infraestructura real en la nube. Ver evidencia completa en
  `docs/evidencia-fase1-carga.md`.
