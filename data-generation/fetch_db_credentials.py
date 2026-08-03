"""Escribe data-generation/.env con las credenciales reales de RDS desde
Secrets Manager, sin imprimir el valor en pantalla en ningún momento.

Se ejecuta como archivo (no como comando pegado en la terminal) para evitar
problemas de escapado de comillas al copiar/pegar comandos multilínea.

Uso:
    python3 fetch_db_credentials.py
"""

import json
import subprocess
import sys

SECRET_ID = "finbank/dev/rds/credentials"
AWS_PROFILE = "prueba-tecnica-finbank"


def main() -> int:
    result = subprocess.run(
        [
            "aws", "secretsmanager", "get-secret-value",
            "--profile", AWS_PROFILE,
            "--secret-id", SECRET_ID,
            "--query", "SecretString",
            "--output", "text",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("ERROR al leer el secreto:", result.stderr, file=sys.stderr)
        return 1

    creds = json.loads(result.stdout)

    with open(".env", "w", encoding="utf-8") as f:
        f.write(f"DB_HOST={creds['host']}\n")
        f.write(f"DB_PORT={creds['port']}\n")
        f.write(f"DB_NAME={creds['dbname']}\n")
        f.write(f"DB_USER={creds['username']}\n")
        f.write(f"DB_PASSWORD={creds['password']}\n")

    print("OK: .env escrito correctamente. Ningún valor fue impreso en pantalla.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
