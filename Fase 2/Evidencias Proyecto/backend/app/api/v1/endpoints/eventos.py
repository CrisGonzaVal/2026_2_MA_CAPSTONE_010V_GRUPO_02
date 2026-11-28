"""Canal de actualizacion en tiempo real por SSE (Feature 028, T5).

Router delgado de **solo lectura**: no consulta ni muta datos de negocio. La
identidad, la institucion, el rol, las capacidades y la expiracion se resuelven
en `contexto_tiempo_real` (dependencia no generadora que cierra la sesion antes
de devolver); el generador del flujo solo lee esa copia inmutable y espera
eventos del bus, de modo que la conexion no retiene una sesion del pool.

El contrato (spec §6.1/§6.2) es:

* `200` con `text/event-stream; charset=utf-8`, `Cache-Control: no-store` y
  `X-Accel-Buffering: no`;
* un frame `listo` con los dominios visibles, frames `cambio` por sobre y
  comentarios `: latido`;
* sin `id:` ni `retry:` y sin identificadores de institucion, usuario o
  recurso en ningun frame;
* cierre limpio en `min(exp - MARGEN_RELOJ_SEGUNDOS, ahora + vida maxima)`;
* `503` con `detail` si el interruptor `TIEMPO_REAL_HABILITADO` esta apagado,
  sin abrir el flujo.

Cada conexion recibe el sobre ya filtrado por servidor (`_dominios_visibles_del_sobre`):
institucion, audiencia de dueno para `pedidos`, visibilidad por rol/capacidad y
la marca sintetica `dashboard`. El frame nunca serializa identificadores del
sobre.

La degradacion del bus (T7) no cierra el HTTP: si `suscribir` o `recibir`
levantan `ErrorBusEventos`, se emite una unica transicion `estado: degradado`,
se espera con retroceso 1/2/4/8/10 s (con latidos y sin abrir otra peticion),
y al volver el bus se emite `estado: recuperado`. `listo` solo se emite cuando
la suscripcion esta activa. La apertura, cada transicion y el cierre dejan una
linea `compustock.tiempo_real` sin PII.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api import dependencies
from app.api.dependencies import ContextoTiempoReal, contexto_tiempo_real
from app.core import eventos as bus_eventos
from app.core.config import settings
from app.core.eventos import LOGGER_BUS, ErrorBusEventos, SobreEvento
from app.core.observabilidad import registrar_tiempo_real

router = APIRouter(prefix="/eventos", tags=["Eventos"])

#: Orden canonico y estable de los dominios en el frame.
ORDEN_DOMINIOS: tuple[str, ...] = (
    "pedidos",
    "inventario",
    "compras",
    "dashboard",
)

#: Comentario de flujo que mantiene viva la conexion sin ser un frame.
LATIDO = ": latido\n\n"

#: Retroceso interno del suscriptor ante un bus caido. Tras el ultimo valor se
#: mantiene el tope de 10 s mientras dure la degradacion (plan §5.4).
RETROCESO_SEGUNDOS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 10.0)


def retroceso_de_intento(intento: int) -> float:
    """Retroceso del intento 0-based; los intentos sobrantes usan el tope."""
    indice = min(max(intento, 0), len(RETROCESO_SEGUNDOS) - 1)
    return RETROCESO_SEGUNDOS[indice]


async def _dormir(segundos: float) -> None:
    """Costura de espera del retroceso; los tests la sustituyen."""
    await asyncio.sleep(segundos)


async def _esperar_retroceso(
    segundos: float,
    latido: float,
    limite: float,
) -> AsyncIterator[str]:
    """Espera el retroceso en tramos de latido, sin pasar el limite de vida.

    Devuelve un comentario `: latido` por tramo para que la conexion degradada
    siga viva y el cliente distinga una conexion colgada de una en espera.
    """
    pendiente = segundos
    while pendiente > 0:
        restante = limite - time.time()
        if restante <= 0:
            return
        tramo = min(pendiente, latido, restante)
        await _dormir(tramo)
        pendiente -= tramo
        yield LATIDO


async def _cerrar_suscripcion(
    suscripcion: bus_eventos.SuscripcionEventos,
) -> None:
    """Cierra una suscripcion sin que un fallo de cierre rompa el flujo."""
    try:
        await suscripcion.cerrar()
    except Exception:  # noqa: BLE001 - el cierre es best-effort
        pass


def _motivo_de_cierre(
    contexto: ContextoTiempoReal, *, ahora: float | None = None
) -> str:
    """Causa del cierre para la linea semantica: token o vida maxima."""
    momento = time.time() if ahora is None else ahora
    if contexto.expira_en is not None:
        limite_token = contexto.expira_en - settings.MARGEN_RELOJ_SEGUNDOS
        if limite_token <= momento + settings.VIDA_MAXIMA_CONEXION_SEGUNDOS:
            return "token_expirado"
    return "vida_maxima"


def _frame(evento: str, datos: dict[str, object]) -> str:
    """Serializa un frame SSE; el `data` es JSON compacto y sin datos de negocio."""
    contenido = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    return f"event: {evento}\ndata: {contenido}\n\n"


def _ordenar_dominios(dominios: frozenset[str] | set[str]) -> list[str]:
    """Devuelve los dominios en el orden cerrado del contrato."""
    return [dominio for dominio in ORDEN_DOMINIOS if dominio in dominios]


#: Roles que reciben los `pedidos` de toda la institucion. El Solicitante solo
#: recibe los pedidos en cuyo `usuario_ids` figura: la audiencia se resuelve en
#: servidor y nunca por el cliente (spec §5.3, D-5).
ROLES_CON_PEDIDOS_DE_LA_INSTITUCION: frozenset[str] = frozenset(
    {"Administrador", "Bodeguero"}
)


def _en_audiencia_de_pedidos(
    contexto: ContextoTiempoReal, sobre: SobreEvento
) -> bool:
    """`True` si la conexion esta en la audiencia del dominio `pedidos`.

    Administrador y Bodeguero reciben los pedidos de la institucion; el
    Solicitante, solo los suyos. La comprobacion ocurre **antes** de sintetizar
    cualquier marca: un pedido ajeno no produce ni dominio ni `dashboard`
    (guardrail de AC-16/D-5).
    """
    return (
        contexto.rol in ROLES_CON_PEDIDOS_DE_LA_INSTITUCION
        or contexto.usuario_id in sobre.usuario_ids
    )


def _dominios_visibles_del_sobre(
    contexto: ContextoTiempoReal, sobre: SobreEvento
) -> tuple[list[str], str] | None:
    """Filtra un sobre del bus para **una** conexion (spec §5.3, D-5/D-13).

    Orden del filtro: institucion -> audiencia de dueno de `pedidos` ->
    visibilidad por rol/capacidad -> marca `dashboard`. Devuelve los dominios
    ordenados y el motivo del frame, o `None` si la conexion no debe recibir
    ninguno.

    La marca `dashboard` se sintetiza como maximo una vez, solo cuando el
    dominio oculto es `pedidos` o `inventario` y la conexion tiene la capacidad
    `dashboard`; nunca convive con el dominio que sustituye y normaliza el
    motivo a `cambio`, sin revelar el motivo real del dominio oculto. `compras`
    no afecta al dashboard. El resultado no copia `institucion_id`,
    `usuario_ids` ni ningun id del sobre: el frame solo lleva dominios y motivo.
    """
    if sobre.institucion_id != contexto.institucion_id:
        return None

    visibles: set[str] = set()
    con_marca_dashboard = False

    if "pedidos" in sobre.dominios and _en_audiencia_de_pedidos(contexto, sobre):
        if "pedidos" in contexto.dominios_visibles:
            visibles.add("pedidos")
        elif "dashboard" in contexto.dominios_visibles:
            con_marca_dashboard = True

    if "inventario" in sobre.dominios:
        if "inventario" in contexto.dominios_visibles:
            visibles.add("inventario")
        elif "dashboard" in contexto.dominios_visibles:
            con_marca_dashboard = True

    if "compras" in sobre.dominios and "compras" in contexto.dominios_visibles:
        visibles.add("compras")

    if con_marca_dashboard:
        visibles.add("dashboard")

    if not visibles:
        return None

    motivo = "cambio" if con_marca_dashboard else sobre.motivo
    return _ordenar_dominios(visibles), motivo


def limite_de_conexion(
    contexto: ContextoTiempoReal, *, ahora: float | None = None
) -> float:
    """Instante de cierre: `min(exp - MARGEN, ahora + VIDA_MAXIMA)`.

    La expiracion es la del token ya validado por Clerk (`exp` en segundos
    epoch); el margen de reloj evita que el flujo siga abierto con una
    credencial vencida. Sin `exp` (fixtures antiguas) solo aplica la vida
    maxima.
    """
    momento = time.time() if ahora is None else ahora
    limite = momento + settings.VIDA_MAXIMA_CONEXION_SEGUNDOS
    if contexto.expira_en is not None:
        limite = min(
            limite, contexto.expira_en - settings.MARGEN_RELOJ_SEGUNDOS
        )
    return limite


def _respuestas_del_canal() -> dict[int, dict[str, object]]:
    """Respuestas documentadas de la operacion, incluido el media type del flujo.

    La excepcion de `response_model` (AGENTS.md §6) queda explicita en el 200:
    el cuerpo es un flujo de texto, no un documento JSON, y la ruta no se oculta
    de `/openapi.json`.
    """
    respuestas: dict[int, dict[str, object]] = dict(
        dependencies.respuestas_de_autorizacion()
    )
    respuestas[status.HTTP_200_OK] = {
        "description": (
            "Flujo SSE abierto. Cada frame termina en una linea vacia: "
            "`listo` con los dominios visibles; `cambio` con los dominios y el "
            "motivo; `estado` con la degradacion o recuperacion del bus; y "
            "comentarios `: latido`. Sin `id:`, sin `retry:` y sin "
            "identificadores de institucion, usuario o recurso."
        ),
        "content": {
            "text/event-stream": {
                "schema": {"type": "string"},
                "example": (
                    'event: listo\ndata: {"dominios":["pedidos","inventario"]}'
                    "\n\n: latido\n\n"
                ),
            }
        },
    }
    respuestas[status.HTTP_429_TOO_MANY_REQUESTS] = {
        "description": (
            "Limite de tasa excedido (Feature 025); conserva el cuerpo JSON "
            "comun y la cabecera `Retry-After`."
        )
    }
    respuestas[status.HTTP_503_SERVICE_UNAVAILABLE] = {
        "description": (
            "Canal deshabilitado por configuracion "
            "(`TIEMPO_REAL_HABILITADO=false`): responde `detail` y no se abre "
            "ningun flujo ni suscripcion al bus."
        )
    }
    return respuestas


async def generar(contexto: ContextoTiempoReal) -> AsyncIterator[str]:
    """Genera `listo`, los `cambio` del bus y los latidos hasta el cierre.

    Sigue el orden del plan §5.4: se **suscribe primero** (cierra la carrera
    entre la lectura y la suscripcion) y `listo` solo se emite cuando la
    suscripcion quedo activa. La espera de cada vuelta es `min(latido,
    restante)`; un `None` de la suscripcion es un latido y no un error.

    Si el bus falla al suscribir o al recibir, el flujo **no se cierra**: se
    emite una unica transicion `estado: degradado`, se libera la suscripcion y
    se reintenta con retroceso 1/2/4/8/10 s (con latidos y sin abrir otra
    peticion HTTP). Al volver el bus se emite `estado: recuperado`; `listo` no
    se repite. Al vencer el limite se cierra limpiamente, sin frame de error.
    """
    if contexto.expira_en is None:
        # En produccion `resolver_identidad` copia el `exp` del token validado;
        # una identidad sin el (solo fixtures) cae en la vida maxima.
        logging.getLogger(LOGGER_BUS).warning(
            "conexion_tiempo_real_sin_expiracion",
            extra={"request_id": contexto.request_id},
        )

    limite = limite_de_conexion(contexto)
    motivo_cierre = _motivo_de_cierre(contexto)
    canal = bus_eventos.canal_de_institucion(contexto.institucion_id)
    suscripcion: bus_eventos.SuscripcionEventos | None = None
    listo_emitido = False
    degradado = False
    intento = 0
    try:
        while True:
            restante = limite - time.time()
            if restante <= 0:
                break

            if suscripcion is None:
                try:
                    suscripcion = (
                        await bus_eventos.obtener_almacen().suscribir(canal)
                    )
                except ErrorBusEventos:
                    if not degradado:
                        degradado = True
                        registrar_tiempo_real(
                            "degradada",
                            "bus",
                            request_id=contexto.request_id,
                        )
                        yield _frame("estado", {"estado": "degradado"})
                    async for latido in _esperar_retroceso(
                        retroceso_de_intento(intento),
                        float(settings.TIEMPO_REAL_LATIDO_SEGUNDOS),
                        limite,
                    ):
                        yield latido
                    intento += 1
                    continue

                if not listo_emitido:
                    registrar_tiempo_real(
                        "abierta",
                        "sesion",
                        request_id=contexto.request_id,
                    )
                    yield _frame(
                        "listo",
                        {
                            "dominios": _ordenar_dominios(
                                contexto.dominios_visibles
                            )
                        },
                    )
                    listo_emitido = True
                if degradado:
                    degradado = False
                    registrar_tiempo_real(
                        "recuperada",
                        "bus",
                        request_id=contexto.request_id,
                    )
                    yield _frame("estado", {"estado": "recuperado"})
                intento = 0

            espera = min(float(settings.TIEMPO_REAL_LATIDO_SEGUNDOS), restante)
            try:
                sobre = await suscripcion.recibir(espera)
            except ErrorBusEventos:
                await _cerrar_suscripcion(suscripcion)
                suscripcion = None
                if not degradado:
                    degradado = True
                    registrar_tiempo_real(
                        "degradada",
                        "bus",
                        request_id=contexto.request_id,
                    )
                    yield _frame("estado", {"estado": "degradado"})
                async for latido in _esperar_retroceso(
                    retroceso_de_intento(intento),
                    float(settings.TIEMPO_REAL_LATIDO_SEGUNDOS),
                    limite,
                ):
                    yield latido
                intento += 1
                continue

            if sobre is None:
                yield LATIDO
                continue
            filtrado = _dominios_visibles_del_sobre(contexto, sobre)
            if filtrado is None:
                # El sobre no aporta ningun dominio visible a esta conexion:
                # no se emite frame (ni se revela el dominio oculto).
                continue
            dominios, motivo = filtrado
            yield _frame(
                "cambio",
                {"dominios": dominios, "motivo": motivo},
            )
    except (GeneratorExit, asyncio.CancelledError):
        motivo_cierre = "cliente"
        raise
    except Exception:
        motivo_cierre = "error"
        raise
    finally:
        if suscripcion is not None:
            await _cerrar_suscripcion(suscripcion)
        registrar_tiempo_real(
            "cerrada",
            motivo_cierre,
            request_id=contexto.request_id,
        )


@router.get(
    "/",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Abrir el canal de actualizacion en tiempo real",
    description=(
        "**Canal SSE de invalidacion.** Mantiene una conexion por pestana y "
        "anuncia que una vista quedo obsoleta; no transporta datos de negocio. "
        "El cliente relee por los GET existentes y agrupa las rafagas.\n\n"
        "**Autenticacion y ambito.** Bearer de Clerk obligatorio; la matriz "
        "central concede la operacion a Administrador, Bodeguero y Solicitante. "
        "El Superadmin recibe **403**. La institucion sale **solo** de la "
        "identidad: `?institucion_id`, `?sede_id`, `?usuario_id` y `?dominios` "
        "no existen y, si llegan, se ignoran.\n\n"
        "**Frames.** `listo` (dominios visibles de la conexion), `cambio` "
        "(dominios y motivo), `estado` (`degradado`/`recuperado` cuando el bus "
        "cae o vuelve) y el comentario `: latido` cada "
        "`TIEMPO_REAL_LATIDO_SEGUNDOS` (1-30 s). Ningun frame lleva `id:`, "
        "`retry:`, `institucion_id`, `usuario_id` ni identificadores de "
        "recurso.\n\n"
        "**Ciclo de vida.** La conexion se cierra limpiamente en "
        "`min(exp - MARGEN_RELOJ_SEGUNDOS, ahora + VIDA_MAXIMA_CONEXION_SEGUNDOS)`; "
        "el cliente trata el cierre como renovacion y reabre con un token "
        "vigente. La identidad, la institucion y las capacidades se resolvieron "
        "antes de abrir el flujo y la sesion de base quedo cerrada: el canal no "
        "retiene una conexion del pool.\n\n"
        "**Errores previos al flujo.** **401** sin sesion valida, **403** por "
        "matriz, **429** por el limite de tasa (con `Retry-After`) y **503** "
        "con `detail` si `TIEMPO_REAL_HABILITADO` esta apagado; en ese caso no "
        "se abre el flujo ni se toca el bus.\n\n"
        "**Excepcion de `response_model`.** Esta operacion **no** declara "
        "`response_model` JSON porque el cuerpo es un flujo de texto "
        "`text/event-stream` (AGENTS.md §6). La excepcion queda documentada "
        "aqui y en la respuesta 200; la ruta sigue publicada en el contrato."
    ),
    responses=_respuestas_del_canal(),
)
async def abrir_canal_de_eventos(
    contexto: ContextoTiempoReal = Depends(contexto_tiempo_real),
) -> StreamingResponse:
    """Devuelve el flujo SSE o el 503 del interruptor, sin abrir nada mas."""
    if not settings.TIEMPO_REAL_HABILITADO:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El canal de actualizacion en tiempo real esta deshabilitado"
            ),
        )
    return StreamingResponse(
        generar(contexto),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )
