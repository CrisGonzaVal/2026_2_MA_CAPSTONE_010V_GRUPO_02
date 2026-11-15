/** Raiz relativa de la API. Coincide con el `prefix` de `app/api/v1/api.py`.
 *
 * En 4200 el dev server reenvia `/api` al backend por `proxy.conf.json`; en
 * 8080 nginx hace el proxy del mismo origen. El navegador nunca necesita CORS
 * para la SPA, y no queda un host de desarrollo escrito en el codigo.
 */
export const URL_API = '/api/v1';
