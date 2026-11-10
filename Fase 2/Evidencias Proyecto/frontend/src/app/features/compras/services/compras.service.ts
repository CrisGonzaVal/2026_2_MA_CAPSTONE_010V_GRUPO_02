import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  CoberturaPreviewRespuesta,
  CoberturaPreviewSolicitud,
  FacturaCompra,
  FacturaCompraRegistrar,
  FiltrosOrdenesCompra,
  NecesidadReabastecimiento,
  OrdenCompra,
  OrdenCompraActualizar,
  OrdenCompraCrear,
  Proveedor,
  ProveedorCrear,
  RecepcionRespuesta,
} from '../../../shared/interfaces';
import { URL_API } from '../../../shared/config/url-api';

/**
 * HTTP del reabastecimiento externo y compras (Feature 020).
 *
 * Cubre las diez rutas del plan §4. La logica de estado (que OC se puede editar,
 * emitir, facturar o cancelar) vive en el backend; este servicio solo traduce la
 * intencion de la vista a llamadas HTTP y no replica validaciones.
 *
 * `registrarFactura` y `editarFactura` son el mismo `PUT`: el endpoint es
 * idempotente y crea la factura en `Emitida` o corrige sus metadatos en
 * `Facturada` (AC-5). Se exponen dos nombres para que la vista exprese la
 * intencion sin conocer esa particularidad del contrato.
 */
@Injectable({ providedIn: 'root' })
export class ComprasService {
  private readonly http = inject(HttpClient);

  // --- AC-1: necesidades de reabastecimiento -------------------------------

  /** `GET /compras/necesidades?sede_id=`; sin sede consulta todas las sedes. */
  listarNecesidades(
    sedeId?: number | null,
  ): Observable<NecesidadReabastecimiento[]> {
    let params = new HttpParams();
    if (sedeId !== null && sedeId !== undefined) {
      params = params.set('sede_id', sedeId);
    }
    return this.http.get<NecesidadReabastecimiento[]>(
      `${URL_API}/compras/necesidades`,
      { params },
    );
  }

  // --- AC-2: catalogo global de proveedores --------------------------------

  listarProveedores(): Observable<Proveedor[]> {
    return this.http.get<Proveedor[]>(`${URL_API}/compras/proveedores`);
  }

  // --- Feature 021 (AC-2): preview de cobertura ----------------------------

  /**
   * `POST /compras/cobertura/preview`: simula la asignacion automatica de una
   * compra hipotetica sobre los pedidos `EnCurso` de la sede.
   *
   * No persiste, no reserva stock y no cambia estados; es idempotente. El
   * servidor responde 404 (sede/producto ajeno o inexistente), 409 (producto
   * inactivo o repetido) y 422 (cuerpo invalido).
   */
  previsualizarCobertura(
    datos: CoberturaPreviewSolicitud,
  ): Observable<CoberturaPreviewRespuesta> {
    return this.http.post<CoberturaPreviewRespuesta>(
      `${URL_API}/compras/cobertura/preview`,
      datos,
    );
  }

  crearProveedor(datos: ProveedorCrear): Observable<Proveedor> {
    return this.http.post<Proveedor>(
      `${URL_API}/compras/proveedores`,
      datos,
    );
  }

  // --- AC-3/AC-4: ordenes de compra ----------------------------------------

  crearOrden(datos: OrdenCompraCrear): Observable<OrdenCompra> {
    return this.http.post<OrdenCompra>(`${URL_API}/compras/ordenes`, datos);
  }

  /**
   * `GET /compras/ordenes` con los filtros del Administrador.
   *
   * El Bodeguero no elige filtros: el servidor lo fuerza a `Facturada` y a su
   * propia sede, ignorando cualquier query que llegue (AC-6). Enviarlos aqui no
   * cambia su ambito, por eso la vista de bodega llama sin argumentos.
   */
  listarOrdenes(
    filtros: FiltrosOrdenesCompra = {},
  ): Observable<OrdenCompra[]> {
    let params = new HttpParams();
    if (filtros.estado !== null && filtros.estado !== undefined) {
      params = params.set('estado', filtros.estado);
    }
    if (filtros.sede_id !== null && filtros.sede_id !== undefined) {
      params = params.set('sede_id', filtros.sede_id);
    }
    return this.http.get<OrdenCompra[]>(`${URL_API}/compras/ordenes`, {
      params,
    });
  }

  actualizarOrden(
    ordenId: number,
    datos: OrdenCompraActualizar,
  ): Observable<OrdenCompra> {
    return this.http.put<OrdenCompra>(
      `${URL_API}/compras/ordenes/${ordenId}`,
      datos,
    );
  }

  emitirOrden(ordenId: number): Observable<OrdenCompra> {
    return this.http.post<OrdenCompra>(
      `${URL_API}/compras/ordenes/${ordenId}/emitir`,
      null,
    );
  }

  // --- AC-5: factura del proveedor -----------------------------------------

  registrarFactura(
    ordenId: number,
    datos: FacturaCompraRegistrar,
  ): Observable<FacturaCompra> {
    return this.http.put<FacturaCompra>(
      `${URL_API}/compras/ordenes/${ordenId}/factura`,
      datos,
    );
  }

  /** Alias de `registrarFactura`: el contrato es un unico `PUT` idempotente. */
  editarFactura(
    ordenId: number,
    datos: FacturaCompraRegistrar,
  ): Observable<FacturaCompra> {
    return this.registrarFactura(ordenId, datos);
  }

  // --- AC-7…AC-11: recepcion fisica ----------------------------------------

  /** Confirma la recepcion total; el cuerpo va vacio (DT-8). */
  recepcionar(ordenId: number): Observable<RecepcionRespuesta> {
    return this.http.post<RecepcionRespuesta>(
      `${URL_API}/compras/ordenes/${ordenId}/recepcion`,
      null,
    );
  }

  // --- AC-12: cancelacion ---------------------------------------------------

  cancelarOrden(
    ordenId: number,
    motivoCancelacion: string,
  ): Observable<OrdenCompra> {
    return this.http.post<OrdenCompra>(
      `${URL_API}/compras/ordenes/${ordenId}/cancelar`,
      { motivo_cancelacion: motivoCancelacion },
    );
  }
}
