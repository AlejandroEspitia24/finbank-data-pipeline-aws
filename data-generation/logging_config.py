"""Configuración de logging compartida por los scripts de generación y carga de datos."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_file: Path | None = None, level: int = logging.INFO) -> None:
    """Configura logging a consola y, opcionalmente, a un archivo.

    Escribir a archivo además de consola importa aquí porque este mismo log
    de ejecución es el precedente del "log de ingesta" que exige la capa
    Bronze del pipeline (Fase 3): mismo patrón, para no rehacerlo después.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
