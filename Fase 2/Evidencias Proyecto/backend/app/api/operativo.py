"""Rutas operativas fuera de `/api/v1` (Feature 024).

`/ready` y `/metrics` no son API de negocio: no exigen Clerk, no figuran en
`MATRIZ_PERMISOS` ni en `/openapi.json` y nginx no las publica. `/health`
conserva su sitio y su contrato en `main.py`.
"""

import logging

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from app.api import dependencies
from app.core.metricas import TIPO_CONTENIDO, generar_exposicion
from app.core.observabilidad import LOGGER_SALUD, identificador_actual
from app.services.salud_service import comprobar_conectividad

router_operativo = APIRouter()


@router_operativo.get(
    "/ready",
    include_in_schema=False,
    summary="Disponibilidad del servicio y su base de datos",
    description=(
        "Sonda operativa: comprueba la conectividad con la base y responde 200 "
        "cuando puede atender trafico o 503 cuando no. No forma parte del "
        "contrato OpenAPI ni de la matriz de permisos."
    ),
)
def verificar_disponibilidad(
    motor: Engine = Depends(dependencies.obtener_motor_readiness),
) -> JSONResponse:
    disponible, error = comprobar_conectividad(motor)
    if disponible:
        return JSONResponse(
            {"status": "ready"}, status_code=status.HTTP_200_OK
        )

    logging.getLogger(LOGGER_SALUD).warning(
        "readiness_fallida",
        extra={
            "request_id": identificador_actual(),
            "error_type": error,
        },
    )
    return JSONResponse(
        {"status": "not_ready"},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@router_operativo.get(
    "/metrics",
    include_in_schema=False,
    summary="Metricas Prometheus del proceso",
    description=(
        "Exposicion en formato texto de Prometheus. Ruta operativa fuera de "
        "OpenAPI y de la matriz; nginx no la publica."
    ),
)
def exponer_metricas() -> Response:
    return Response(content=generar_exposicion(), media_type=TIPO_CONTENIDO)
