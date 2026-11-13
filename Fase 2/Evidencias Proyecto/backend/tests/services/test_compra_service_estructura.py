"""Contrato estructural del paquete `app.services.compra_service` (Feature 023).

No prueba comportamiento de negocio: fija la forma del paquete, la fachada y
las firmas publicas para que el refactor no cambie la costura que consumen los
endpoints, `ticket_service` y los tests.

Antes de la Feature 023 este archivo falla en la primera asercion, porque
`compra_service` todavia es un modulo y no un paquete.
"""

from __future__ import annotations

import inspect
from dataclasses import fields, is_dataclass
from pathlib import Path

from app.services import compra_service

DIRECTORIO_SERVICIOS = Path(__file__).resolve().parents[2] / "app" / "services"
DIRECTORIO_PAQUETE = DIRECTORIO_SERVICIOS / "compra_service"

MODULOS_ESPERADOS = {
    "__init__.py",
    "_comun.py",
    "cobertura.py",
    "necesidades.py",
    "ordenes.py",
    "proveedores.py",
    "recepcion.py",
}

SIMBOLOS_PUBLICOS = {
    "institucion_de_compras",
    "listar_necesidades_reabastecimiento",
    "previsualizar_cobertura",
    "listar_proveedores",
    "crear_proveedor",
    "listar_ordenes_compra",
    "crear_orden_compra",
    "actualizar_orden_compra",
    "emitir_orden_compra",
    "registrar_o_editar_factura",
    "cancelar_orden_compra",
    "calcular_cobertura_tickets",
    "recepcionar_orden_compra",
    "orden_a_respuesta",
    "SimulacionTicketProducto",
    "_simular_claves",
}

_POK = inspect.Parameter.POSITIONAL_OR_KEYWORD
_KW = inspect.Parameter.KEYWORD_ONLY
_SIN_DEFECTO = inspect.Parameter.empty

FIRMAS_ESPERADAS = {
    "institucion_de_compras": [
        ("db", _POK, _SIN_DEFECTO),
        ("identidad", _POK, _SIN_DEFECTO),
    ],
    "listar_necesidades_reabastecimiento": [
        ("db", _POK, _SIN_DEFECTO),
        ("institucion_id", _POK, _SIN_DEFECTO),
        ("sede_id", _POK, None),
    ],
    "previsualizar_cobertura": [
        ("db", _POK, _SIN_DEFECTO),
        ("datos", _POK, _SIN_DEFECTO),
        ("identidad", _POK, _SIN_DEFECTO),
    ],
    "listar_proveedores": [
        ("db_control", _POK, _SIN_DEFECTO),
    ],
    "crear_proveedor": [
        ("db_control", _POK, _SIN_DEFECTO),
        ("db_tenant", _POK, _SIN_DEFECTO),
        ("datos", _POK, _SIN_DEFECTO),
        ("identidad", _POK, _SIN_DEFECTO),
    ],
    "listar_ordenes_compra": [
        ("db", _POK, _SIN_DEFECTO),
        ("identidad", _POK, _SIN_DEFECTO),
        ("estado", _KW, None),
        ("sede_id", _KW, None),
    ],
    "crear_orden_compra": [
        ("db_tenant", _POK, _SIN_DEFECTO),
        ("db_control", _POK, _SIN_DEFECTO),
        ("datos", _POK, _SIN_DEFECTO),
        ("identidad", _POK, _SIN_DEFECTO),
    ],
    "actualizar_orden_compra": [
        ("db_tenant", _POK, _SIN_DEFECTO),
        ("db_control", _POK, _SIN_DEFECTO),
        ("orden_id", _POK, _SIN_DEFECTO),
        ("datos", _POK, _SIN_DEFECTO),
        ("identidad", _POK, _SIN_DEFECTO),
    ],
    "emitir_orden_compra": [
        ("db_tenant", _POK, _SIN_DEFECTO),
        ("orden_id", _POK, _SIN_DEFECTO),
        ("identidad", _POK, _SIN_DEFECTO),
    ],
    "registrar_o_editar_factura": [
        ("db_tenant", _POK, _SIN_DEFECTO),
        ("orden_id", _POK, _SIN_DEFECTO),
        ("datos", _POK, _SIN_DEFECTO),
        ("identidad", _POK, _SIN_DEFECTO),
    ],
    "cancelar_orden_compra": [
        ("db_tenant", _POK, _SIN_DEFECTO),
        ("orden_id", _POK, _SIN_DEFECTO),
        ("datos", _POK, _SIN_DEFECTO),
        ("identidad", _POK, _SIN_DEFECTO),
    ],
    "calcular_cobertura_tickets": [
        ("db", _POK, _SIN_DEFECTO),
        ("sede_id", _POK, _SIN_DEFECTO),
        ("producto_ids", _POK, None),
    ],
    "recepcionar_orden_compra": [
        ("db_tenant", _POK, _SIN_DEFECTO),
        ("orden_id", _POK, _SIN_DEFECTO),
        ("identidad", _POK, _SIN_DEFECTO),
    ],
    "orden_a_respuesta": [
        ("orden", _POK, _SIN_DEFECTO),
    ],
    "_simular_claves": [
        ("db", _POK, _SIN_DEFECTO),
        ("institucion_id", _POK, _SIN_DEFECTO),
        ("claves", _POK, _SIN_DEFECTO),
        ("cantidades_oc", _POK, None),
        ("bloquear", _POK, False),
    ],
}

CAMPOS_SIMULACION = (
    "ticket_id",
    "asunto",
    "solicitante_nombre",
    "solicitante_apellido",
    "solicitante_correo",
    "prioridad_nombre",
    "fecha_creacion",
    "solicitado",
    "plan_previo",
    "cubierto_stock",
    "entregado",
    "necesidad",
    "asignada",
    "faltante",
    "cobertura",
)


def test_el_servicio_es_un_paquete_con_los_modulos_esperados() -> None:
    assert hasattr(compra_service, "__path__"), (
        "compra_service debe ser un paquete desde la Feature 023"
    )
    assert Path(compra_service.__file__).name == "__init__.py"
    assert not (DIRECTORIO_SERVICIOS / "compra_service.py").exists(), (
        "el modulo plano no debe sobrevivir al paquete"
    )
    modulos = {ruta.name for ruta in DIRECTORIO_PAQUETE.iterdir() if ruta.is_file()}
    assert modulos == MODULOS_ESPERADOS


def test_la_fachada_reexporta_la_api_publica() -> None:
    assert set(compra_service.__all__) == SIMBOLOS_PUBLICOS
    for nombre in sorted(SIMBOLOS_PUBLICOS):
        assert hasattr(compra_service, nombre), f"falta el simbolo {nombre}"
        objeto = getattr(compra_service, nombre)
        assert objeto is not None
        assert objeto.__module__.startswith("app.services.compra_service."), (
            f"{nombre} debe venir de un modulo del paquete, no de la fachada"
        )


def test_las_firmas_publicas_y_el_dto_no_cambian() -> None:
    for nombre, esperada in FIRMAS_ESPERADAS.items():
        funcion = getattr(compra_service, nombre)
        obtenida = [
            (parametro.name, parametro.kind, parametro.default)
            for parametro in inspect.signature(funcion).parameters.values()
        ]
        assert obtenida == esperada, f"la firma de {nombre} cambio"

    assert is_dataclass(compra_service.SimulacionTicketProducto)
    nombres_campos = tuple(
        campo.name for campo in fields(compra_service.SimulacionTicketProducto)
    )
    assert nombres_campos == CAMPOS_SIMULACION
