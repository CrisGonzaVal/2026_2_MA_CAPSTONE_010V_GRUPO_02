# Feature 028: Actualización en tiempo real de pedidos y tablero

**Estado:** aprobada (28/Nov/2026); validación @reviewer: APROBADO (28/Nov/2026)
**Release:** 2.0 — Sprint 7 (prioritaria: se implementa antes de 015 y 016)
**Tipo:** Sincronización push servidor→cliente con eventos de invalidación; sin cambio de modelo de datos
**Sucede a:** Feature 027 (validación de entradas y errores de contrato, cerrada el 24/Nov/2026)
**Hito:** 2 — 11/Dic/2026

> **Nota de relación con la 016.** Esta feature es la **antesala técnica** de la Feature 016
> (notificaciones in-app), que sigue pendiente y no se absorbe aquí. La 028 entrega el
> **transporte** de cambios en vivo y la invalidación de vistas; **no** crea un centro de
> notificaciones, no persiste avisos, no envía correo ni push y no decide qué merece
> notificarse. Esas decisiones pertenecen a la 016.

## 1. Problema

### 1.1 Cada vista es una fotografía que nunca se vuelve a tomar

Hoy la aplicación lee una sola vez y no se vuelve a sincronizar:

- El tablero de pedidos carga sus datos al abrirse y solo cambia cuando el usuario navega,
  recarga la página o ejecuta una acción desde esa misma pestaña.
- El detalle de un pedido carga cabecera, ítems e historial al entrar; si otro usuario aprueba,
  retira, confirma, anula, rechaza o edita el mismo pedido, la vista queda mostrando el estado
  anterior.
- El dashboard consolidado se lee una vez al montarse; sus KPI, el log de alertas y la
  actividad reciente no se actualizan aunque el stock o los pedidos cambien.
- La recepción de una orden de compra que desbloquea pedidos `EnCurso` no produce ningún aviso:
  el Bodeguero que tenía el detalle abierto sigue viendo el pedido sin disponibilidad y el
  Solicitante sigue viendo la etiqueta de proceso anterior.

No existe sondeo periódico ni canal de eventos: la única sincronización disponible es la
recarga manual del navegador. El propio discurso del producto promete «consultar disponibilidad
en tiempo real», pero hoy esa promesa solo es cierta en el instante de la carga.

### 1.2 Consecuencias operativas

- **Tableros divergentes.** Dos usuarios de la misma institución ven columnas distintas para el
  mismo conjunto de pedidos. La demostración del Hito 2 necesita dos sesiones simultáneas y hoy
  cada una cuenta una historia diferente.
- **Decisiones sobre datos obsoletos.** Un Bodeguero intenta retirar un pedido que el
  Administrador ya anuló; el servidor responde 409 y la interfaz parece rota cuando en realidad
  estaba desactualizada. Lo mismo ocurre con una confirmación de entrega o una segunda
  anulación.
- **Trabajo duplicado y pérdida de confianza.** El usuario repite la acción, recarga, o pide al
  compañero que «refresque» para comprobar si el cambio llegó.
- **Indicadores congelados.** El dashboard puede mostrar un stock, un conteo de pedidos activos
  o una alerta que ya no corresponden a la base; la actividad reciente no refleja la recepción
  que acaba de ocurrir.
- **El desbloqueo por compras es invisible.** La regla de la 021 (recepción que cubre pedidos
  `EnCurso`) solo se descubre al volver a entrar al detalle.

### 1.3 Lo que ya existe y hace viable la solución

- La SPA y la API comparten origen (`/api/v1`): en desarrollo mediante el proxy del servidor de
  Angular y en 8080 mediante nginx. No hace falta abrir un canal cross-origin ni un puerto
  nuevo.
- Clerk ya emite el Bearer de sesión y la API lo valida por JWKS; la autorización por rol vive en
  una matriz central y el aislamiento por institución en esquemas PostgreSQL separados.
- Existe infraestructura efímera de Redis desde la Feature 025: el servidor está en el Compose y
  el cliente del backend ya está instalado. El bus de eventos puede reutilizarla sin añadir
  paquetes.
- El borde de la 024 ya proxifica `/api/`, aplica límites y conserva `X-Request-ID`; falta
  únicamente permitir respuestas de larga duración sin almacenamiento en búfer.
- El límite distribuido de la 025 (120 peticiones por minuto por IP) obliga a que el canal sea
  económico: una conexión por pestaña y reconexiones acotadas, no un sondeo.

### 1.4 Por qué no alcanza con polling

El sondeo periódico fue descartado con el usuario. Aunque técnicamente resolvería la
actualización, su costo crece con el número de pestañas y de vistas abiertas, su latencia es
función del intervalo y consume el presupuesto de 120 peticiones por minuto por IP sin que haya
cambios que entregar. Un canal push entrega el cambio cuando ocurre, no cuando toca preguntar.

## 2. Objetivo

Que un cambio confirmado en un pedido —o en el stock que afecta su disponibilidad— se refleje
**sin recargar la página y sin acción del usuario** en las vistas autorizadas de los demás
usuarios de la misma institución: tablero, detalle del pedido y dashboard, incluidos los cambios
derivados de una recepción de orden de compra que desbloquea pedidos y de las mutaciones de OC que
alteran la cadena del pedido (emisión, facturación y cancelación).

Al cierre:

1. Un cambio de pedido hecho en una sesión se ve en otra sesión autorizada en **5 segundos o
   menos**, sin recargar ni pulsar nada.
2. **Toda mutación confirmada intenta publicar** con el bus sano; la entrega es best-effort y
   no garantizada, y la convergencia es por relectura.
3. **Ningún evento cruza instituciones ni llega a un rol sin acceso**, y ningún evento
   transporta datos de negocio.
4. Si el bus de eventos falla, **la API de negocio responde exactamente igual** que hoy y el
   cliente se recupera solo.
5. El canal funciona en **4200 y en 8080**, y el presupuesto de tasa no se agota por
   reconexiones.

## 3. Alcance

### 3.1 Dentro de alcance

- **Canal de eventos push** autenticado con la sesión Clerk existente, de una sola vía
  servidor→cliente, con latido, renovación atada a la credencial y cierre ordenado.
- **Un evento de invalidación por mutación confirmada**, sin datos de negocio, que obliga al
  cliente a releer por las rutas GET ya existentes y autorizadas.
- **Publicación en todas las mutaciones del ciclo de vida del pedido**: alta, edición,
  aprobación, retiro, confirmación de entrega, anulación (desde `EnRevision` y anulación
  administrativa del retiro), rechazo y el cambio de estado de legado.
- **Publicación de los cambios de stock** que afectan la disponibilidad y los indicadores:
  registro manual de movimientos y recepción de orden de compra. La recepción anuncia además
  los pedidos desbloqueados.
- **Publicación de las mutaciones de compras**: emisión, facturación, cancelación y recepción de
  OC. Se añade el dominio `pedidos` cuando la mutación altera la cadena del pedido; las
  mutaciones que no cambian `GET /tickets/{id}` (alta/edición en `Borrador`, proveedores y
  preview) quedan fuera de los criterios.
- **Sincronización de las tres superficies mínimas**: tablero de pedidos, detalle del pedido
  (estado, historial, etiqueta de proceso y disponibilidad) y dashboard (KPI, alertas y
  actividad).
- **Aislamiento por institución, por rol y por dominio**, resuelto en el servidor.
- **Resiliencia**: fail-open del bus, reconexión con retroceso exponencial, pestaña oculta y
  vuelta a foco, agrupación de ráfagas y resincronización tras cada apertura.
- **Gobierno del contrato**: una operación nueva en la matriz central y en `/openapi.json`, con
  su documentación de flujo y de respuestas, y la actualización explícita de las aserciones
  absolutas de cardinalidad.
- **Borde**: ajuste del proxy de nginx para respuestas de larga duración (sin búfer y con
  tiempo de lectura mayor que el latido).
- Pruebas de backend y frontend, evidencia de cierre y sincronización documental.

### 3.2 Fuera de alcance

- **Feature 016 y todo lo que sea notificación persistente**: centro de notificaciones, bandeja,
  contadores de no leídos, marcas de leído, preferencias, correo, push del navegador o SMS.
- **Persistencia, historial o reproducción de eventos.** No hay tabla, cola persistente,
  `Last-Event-ID`, búfer de repetición ni recuperación de eventos perdidos: cada apertura
  resincroniza por GET.
- **Polling como mecanismo principal o de respaldo.** No se añade sondeo periódico.
- **WebSocket.** El canal es unidireccional; no se abre una vía bidireccional.
- **Cambios en las reglas de negocio del pedido, del stock, de compras o de cobertura.** La 028
  solo anuncia lo que ya ocurre; no altera transiciones, permisos, estados, validaciones ni
  fórmulas.
- **Rediseño visual.** No cambia el layout, la navegación ni el sistema visual. Un indicador no
  intrusivo de «actualizaciones en pausa» es opcional y no se exige como criterio.
- **Otras superficies y dominios**: administración de usuarios, sedes y departamentos; catálogo
  de productos y categorías; y las mutaciones de compras que **no** cambian `GET /tickets/{id}`
  (alta y edición en `Borrador`, proveedores y preview de cobertura). El mecanismo debe admitirlas
  sin rediseño, pero no se incluyen como criterios de aceptación. Las mutaciones de OC que sí
  cambian la cadena del pedido —emisión, facturación, cancelación y recepción— **sí** están dentro
  (D-13, Anexo A).
- **Actualización de la vista de existencias** como superficie obligatoria. El stock se difunde
  porque alimenta el dashboard y la disponibilidad del pedido; la vista de inventario puede
  suscribirse después sin cambios de contrato.
- **Filtro por sede dentro de la señal de inventario.** La señal no transporta sede; la lectura
  posterior ya está acotada por rol. Se acepta la exposición de actividad agregada dentro de la
  institución, sin datos ni identificadores.
- **Features 015 y 016**, que siguen pendientes después de esta.

## 4. Decisiones

### D-1 — SSE push real, unidireccional, como único mecanismo de actualización

El servidor empuja eventos al navegador por un flujo de texto sobre HTTP. El cliente no abre un
socket bidireccional ni pregunta periódicamente.

**Por qué:** el único flujo necesario va de servidor a cliente; el refresco de datos ya viaja por
las rutas GET existentes. SSE atraviesa el mismo origen, el mismo proxy y el mismo Bearer sin
infraestructura nueva, y el navegador o el cliente pueden detectar la caída y reconectar con una
política propia.

**Alternativas descartadas:** *WebSocket* — bidireccional innecesario, con handshake,
autorización y ciclo de vida propios que hoy no existen; *polling* — descartado con el usuario
por latencia, costo y consumo del límite de tasa; *long polling* — misma semántica que SSE con
más peticiones y más estados que manejar.

### D-2 — El evento es una señal de invalidación, no un transporte de datos

El evento solo declara **qué dominio cambió y por qué motivo**. No lleva asunto, cantidades,
estado, nombres, correos, stock ni identificadores de negocio. El cliente relee por las rutas GET
existentes: `GET /tickets/`, `GET /tickets/{id}`, `GET /tickets/{id}/historial`, `GET /dashboard/`
y, para el panel de recepciones —fuera de la superficie mínima—, `GET /compras/ordenes`.

**Por qué:** el acotamiento por rol e institución ya vive en los servicios de lectura; si el
evento transportara datos habría que duplicar ese acotamiento en el emisor, con dos
implementaciones que se desincronizan y una superficie nueva de fuga. Además, el dato empujado
puede quedar obsoleto antes de pintarse, mientras que la relectura devuelve siempre el estado
vigente y autorizado. El evento es pequeño y no revela nada que el GET posterior no vaya a
decidir de nuevo.

**Alternativas descartadas:** empujar el DTO completo de cada vista — duplica los read models de
la 004, la 009 y la 013, multiplica los permisos por evento y arriesga fuga; empujar deltas o
parches — obliga a fusionar estados en el cliente, con conflictos y el mismo riesgo de fuga.

**Costo aceptado:** una relectura por vista y por ventana de invalidación. Se agrupa (D-10) y se
mide para que una ráfaga no se convierta en una tormenta de GET.

### D-3 — Un endpoint genérico de eventos, no uno por dominio

Se publica **una sola operación de flujo** para toda la aplicación, no una por dominio.

**Por qué:** el cliente necesita una conexión por pestaña, no una por vista ni una por dominio;
una sola operación mantiene una fila en la matriz, una entrada en `/openapi.json` y un único
ciclo de vida de conexión que probar. El filtrado por dominio y por audiencia se hace por
evento, no por ruta. Varias rutas de flujo multiplicarían conexiones contra el límite de
conexiones del borde y el presupuesto de tasa sin aportar aislamiento: el evento no lleva datos
(D-2).

**Alternativa descartada:** una ruta por dominio (pedidos, inventario, compras) con una conexión
por vista abierta; además de multiplicar el costo, obligaría a repetir en cada ruta la
autorización y el ciclo de vida.

### D-4 — Autorización por la matriz central, sin una capacidad única

La operación se concede a los **tres roles institucionales** (Administrador, Bodeguero y
Solicitante) mediante la matriz central. El Superadmin queda fuera con **403**, coherente con la
Feature 017: no tiene lecturas de negocio y su superficie es `/control/*`.

La operación **no se ata a una capacidad funcional única**, porque el flujo agrega varios
dominios. La disponibilidad de cada dominio se resuelve **por evento**: un evento de pedidos
solo se entrega si el actor puede leer pedidos (matriz y capacidad `tickets`); uno de inventario,
si puede leer inventario (capacidad `inventario`); uno de compras, si puede operar compras
(capacidad `compras`). El conjunto cerrado de siete capacidades de la 012/020 no cambia.

**Por qué:** atar el flujo a `tickets` dejaría sin actualización en vivo a una institución con
`tickets` apagado pero `dashboard` encendido; no atarlo a ninguna capacidad y entregar todos los
dominios revelaría actividad de módulos apagados. La resolución por evento conserva ambas
propiedades sin crear una octava capacidad.

Una conexión con la capacidad **`dashboard`** habilitada pero sin acceso al dominio que cambió
recibe una **marca sintética `dashboard`** en lugar del dominio oculto: el dashboard se refresca
sin que el frame nombre el dominio que el rol no puede ver. La marca se resuelve por conexión y no
lleva el motivo original (D-13).

**Alternativas descartadas:** una capacidad «tiempo real» nueva — rompe el conjunto cerrado y no
aporta; dejar la ruta sin autorización — el evento, aunque no lleve datos, es metadato de
actividad.

### D-5 — Aislamiento por institución, por rol y por propietario, resuelto en servidor

- La institución se deriva **únicamente de la identidad** (correo verificado → mapa de control →
  esquema tenant). Ningún parámetro del cliente elige institución, y un parámetro enviado se
  ignora.
- Un evento de **pedidos** se entrega a Administrador y Bodeguero de la institución (capacidad
  `tickets` habilitada) y al **Solicitante dueño** del pedido; nunca a otro Solicitante de la
  misma institución.
- Un evento de **inventario** se entrega a los roles con lectura de inventario habilitada.
- Un evento de **compras** se entrega a los roles con acceso a compras (Administrador y
  Bodeguero) y capacidad `compras` habilitada.
- El **frame que ve el cliente** no transporta identificadores de recurso, institución ni
  usuario, ni siquiera para el dueño; lo obtiene del GET posterior.

**Sobre interno y frame.** El mensaje interno del bus es distinto del frame del cliente. El sobre
puede llevar `institucion_id`, los `usuario_id` de los dueños a los que se dirige un evento de
pedidos y los dominios de origen; son **metadatos de enrutamiento** y **nunca se serializan**. El
frame solo contiene los dominios visibles para esa conexión, el motivo (o `cambio` si es
sintético) y, en su caso, el estado. La prohibición de identificadores aplica al frame, no al
sobre. Una recepción que desbloquea N pedidos de N dueños se publica **una vez** con el conjunto
de dueños y el fan-out se resuelve por conexión; no se emiten N mensajes ni se expone el conjunto
al cliente.

**Por qué:** un evento sigue siendo información: revela que algo cambió y cuándo. Un Solicitante
no debe descubrir que otro compañero emitió o anuló un pedido, ni un Bodeguero debe recibir
actividad de un módulo que su institución tiene apagado. El cliente no es una frontera de
seguridad: filtrar en el navegador sería una fuga, no un control. Separar el sobre del frame
permite enrutar al dueño sin poner su id en el evento público.

**Alternativas descartadas:** difundir a toda la institución y filtrar en el cliente; difundir
globalmente con la institución en el evento; enviar el recurso afectado en el frame y confiar en
que el cliente no lo muestre; abrir una conexión por dueño.

### D-6 — La conexión se autentica con el Bearer de Clerk y vive atada a esa credencial

El flujo se abre con la **misma cabecera `Authorization: Bearer`** que el resto de la API. No se
acepta token en la URL, en una cookie, en el cuerpo ni en un parámetro; no se crea login
alternativo, JWT local ni sesión de canal. El `EventSource` nativo del navegador no permite
enviar cabeceras: usarlo obligaría a transportar el token en la URL, justo lo que esta decisión
prohíbe. Por eso el flujo se consume con la petición HTTP autenticada habitual y la aplicación
interpreta el formato de eventos.

La conexión **no sobrevive a la credencial**: el servidor la cierra cuando vence el token que la
autenticó; el cliente pide un token vigente a Clerk y reabre el canal sin intervención del
usuario. Si Clerk ya no tiene sesión, la reapertura responde 401 y el cliente **no reintenta**.
Cerrar sesión en la aplicación cierra el canal de inmediato.

La **expiración** se toma del token ya validado, no de un valor fijo: la identidad debe exponerla
o el endpoint resolverla de los claims validados. El cierre se produce en
**`exp - MARGEN_RELOJ_SEGUNDOS`** (10 s), para no anunciar una conexión que vence a mitad de un
frame. Además, la conexión no vive más de **`VIDA_MAXIMA_CONEXION_SEGUNDOS`** (300 s por
defecto), aunque el token dure más; en cada reapertura se **reevalúan la institución y las
capacidades** del actor. La ventana máxima de obsolescencia de una capacidad o de una
desactivación institucional es, por tanto, la menor entre la vigencia del token y esa vida
máxima (§5.5).

**Por qué:** Clerk sigue siendo la única autoridad y el token nunca aparece en historiales,
referrers, logs de proxy ni capturas de URL; además, el fin de sesión y la desactivación de una
institución surten efecto en un plazo acotado y declarado, incluso si la conexión seguía abierta.
El margen de 10 s evita que un frame se emita con una credencial que ya venció. El costo es una
reapertura por vigencia y pestaña, del orden de una petición por minuto —o una cada cinco minutos
si el token dura más—, compatible con el presupuesto de 120/min.

**Alternativas descartadas:** token en query string — queda en historial, logs y referrer, y
sobrevive al cierre de sesión; cookie de sesión — reintroduce un mecanismo de autenticación local
prohibido; ticket de un solo uso — añade una operación, un estado efímero y un segundo tipo de
credencial para el mismo efecto; TTL fijo — miente si Clerk cambia la vigencia.

### D-7 — Sin reproducción: cada apertura resincroniza por GET

El servidor no guarda eventos, no implementa `Last-Event-ID` y no reproduce lo ocurrido durante
una desconexión. Cada apertura o reapertura se trata como una posible pérdida: el cliente relee
las vistas activas. Para cerrar la carrera entre la lectura inicial y la suscripción, el
servidor confirma la suscripción con un frame `listo` y el cliente resincroniza **después** de
recibirlo.

**Por qué:** sin persistencia no hay DDL, no hay retención que limpiar, no hay cursor que
coordinar entre procesos y la fuente de verdad sigue siendo la base. Un evento perdido no es una
actualización perdida: la siguiente relectura converge. Un búfer de repetición en memoria se
perdería al reiniciar y no cubriría a los demás procesos; un registro persistente es exactamente
la 016.

**Alternativas descartadas:** búfer circular con `Last-Event-ID` — estado por proceso,
incompleto y sin garantía tras reinicio; tabla de eventos — DDL, crecimiento, retención y
privacidad que esta feature no necesita.

### D-8 — Publicación después del commit, best-effort y fail-open

Un evento se publica **solo después de que la transacción de la mutación confirme**. Una
mutación rechazada, revertida o que termina en error no publica nada. La publicación es
**best-effort y a lo sumo una vez**: Redis Pub/Sub es *fire-and-forget*, no confirma entrega ni
persiste; con el bus sano toda mutación confirmada **intenta** publicar, pero no se garantiza que
el frame llegue. Si el bus falla, la mutación ya confirmada responde con su status y su cuerpo
habituales; no se convierte en 5xx, no se revierte y no se bloquea más de **0,5 s** (cota dura del
intento de publicación, la misma espera que la 025 usa para Redis). No hay bucle de reintento de
publicación.

**Por qué:** anunciar antes del commit mostraría estados que pueden no existir; hacer depender la
respuesta del bus acoplaría la disponibilidad del negocio a un componente efímero, contra el
fail-open que la 025 ya estableció para Redis. La entrega óptima es no garantizada por diseño: el
cliente no depende de recibir el evento, porque cada apertura, cada vuelta a foco y cada
resincronización releen la fuente de verdad. Un duplicado es posible pero no está garantizado; si
ocurriera, la agrupación y la relectura idempotente lo absorben. Prometer «al menos una vez»
sobre Pub/Sub sería falso.

**Costo aceptado:** con el bus caído, un cambio confirmado puede no anunciarse. La vista se
recupera con la siguiente reapertura, con la vuelta a foco o con la recarga manual; la
convergencia no depende de recibir el evento.

### D-9 — El reparto entre procesos no puede depender de la memoria local

La entrega debe funcionar cuando el backend corre en **más de un proceso o réplica** (la 025 ya
verificó dos workers). Se reutiliza la infraestructura efímera de Redis de la 025 como bus de
distribución: ya está instalada, no persiste y su caída no impide arrancar la API. No se añade
una dependencia nueva.

**Por qué:** un hub en memoria entregaría el evento solo a las pestañas conectadas al mismo
proceso que atendió la mutación; con dos workers, la mitad de los usuarios no vería nada y el
fallo sería silencioso. Redis ya resuelve el reparto y el fail-open está probado en la 025.

**Alternativas descartadas:** hub en memoria — incorrecto con más de un worker; `LISTEN/NOTIFY`
de PostgreSQL — acopla el bus a la base y a sus transacciones; broker externo — infraestructura y
dependencia nuevas para un requisito que Redis ya cubre.

### D-10 — Una conexión por pestaña, refresco agrupado y respeto por la vista

- Cada pestaña mantiene **una sola conexión** de eventos, compartida por todas sus vistas.
- Varios eventos en una ventana corta producen **como máximo un refresco por vista y por
  ventana**; nunca se lanza un refresco si ya hay uno en vuelo, y se permite uno pendiente.
- El refresco es **silencioso**: no reemplaza el contenido por un estado de carga, no reinicia
  filtros, orden, búsqueda ni pestañas, y no cierra diálogos ni borra texto escrito.
- Una pestaña **oculta** no refresca; al volver a foco resincroniza una vez.

**Por qué:** sin agrupación, veinte cambios seguidos dispararían veinte relecturas por vista y
consumirían el presupuesto de tasa; sin preservación de estado, la actualización en vivo sería
peor que no tenerla porque interrumpiría al usuario que está escribiendo un motivo. Una conexión
por pestaña acota las conexiones simultáneas del borde (20 por IP en nginx) y evita que cada
vista compita por su propio canal.

**Alternativas descartadas:** una conexión por vista — multiplica conexiones y peticiones;
refresco inmediato por evento — ráfagas y parpadeo; recarga completa de la ruta — pierde estado
y produce saltos.

### D-11 — El endpoint de flujo se documenta sin `response_model` JSON

La operación declara `status_code=200`, una respuesta de tipo flujo con media type
`text/event-stream` y las respuestas 401, 403, 429 y 503 documentadas, además de la descripción
del formato de frames. **No declara `response_model` JSON** porque el cuerpo no es un documento
JSON: es una secuencia de eventos. Esta es la excepción explícita a la regla de `AGENTS.md` §6, y
se resuelve documentando el contrato en la descripción y en los esquemas de error, no ocultando
la ruta.

**Por qué:** `AGENTS.md` exige que toda ruta tenga contrato y documentación; lo que no puede
exigir es un `response_model` incompatible con un flujo. Ocultarla de `/openapi.json` violaría
la gobernanza y dejaría la operación sin contrato público.

**Alternativa descartada:** un endpoint JSON que devuelva un «ticket de conexión» y luego abra el
flujo — una petición y una credencial más para el mismo resultado.

### D-12 — Sin DDL, sin entidades nuevas, sin persistencia y sin dependencias nuevas

La feature **no toca el modelo de datos**: no crea tablas, columnas, índices, entidades de
dominio, versiones de esquema ni migraciones. El token sigue en **`026.1`**, con **25 tablas en
`control`**, **22 por tenant** y **21 entidades de dominio**. El estado del canal es efímero y
vive en Redis, que tampoco persiste.

No se agrega ningún paquete: el backend ya tiene el **cliente** `redis==8.1.0` y las utilidades de
streaming de la plataforma; el **servidor** del Compose es `redis:7.2-alpine`. El frontend usa
APIs nativas del navegador para consumir y parsear el flujo. Si en la fase de plan apareciera una
dependencia imprescindible, deberá justificarse y verificarse antes de instalarla, pero el punto
de partida es **cero dependencias nuevas**.

**Por qué:** los eventos son señales, no hechos de negocio que deban auditarse; persistirlos
sería el comienzo de la 016 y añadiría retención, privacidad y mantenimiento sin necesidad. La
base se reconstruye, no se migra (`AGENTS.md` §8.8), así que un cambio de DDL sería
desproporcionado.

**Alternativa descartada:** registrar los eventos en una tabla para auditoría o reproducción;
queda para una feature de notificaciones que lo justifique.

### D-13 — Dominios mínimos, marca sintética de dashboard y compras que tocan el pedido

Los dominios **de origen** de la señal son **`pedidos`**, **`inventario`** y **`compras`**. El
frame puede incluir además la marca sintética **`dashboard`**, que el servidor añade **por
conexión** cuando la conexión tiene la capacidad `dashboard` pero no puede ver un dominio de
origen que afecta al dashboard (`pedidos` o `inventario`). La marca no dice qué dominio cambió,
no lleva datos y usa `motivo: "cambio"`: nunca expone el nombre del dominio oculto ni el motivo
real. El dashboard no tiene un evento de origen propio: se invalida con `pedidos` e `inventario`
—visibles o sintetizados—.

`compras` se emite en **todas las mutaciones de OC**: emisión, facturación, cancelación y
recepción. El dominio `pedidos` se añade cuando la mutación cambia lo que devuelve
`GET /tickets/{id}`: emisión con plan que asigna cantidades, facturación que pasa la OC a
`Facturada` con plan, cancelación de una OC `Emitida` con plan y recepción que cambia la cadena o
desbloquea pedidos. No se anuncian las mutaciones de compras que **no** cambian el pedido: alta y
edición en `Borrador`, proveedores y preview de cobertura. Las condiciones exactas están en el
Anexo A.

**Por qué:** el dashboard de la 009 es una lectura derivada de pedidos, stock y organización; un
evento propio duplicaría avisos y obligaría a decidir en dos lugares cuándo invalida. La marca
`dashboard` resuelve el caso de una institución con `tickets` o `inventario` apagados pero
`dashboard` encendido sin revelar el dominio que el rol no puede ver. Las mutaciones de compras
que alteran la cadena del pedido son parte del «cambio del pedido» que el usuario pidió reflejar:
un plan congelado, una factura o una cancelación cambian lo que el Solicitante ve en su detalle.
Las demás no cambian `GET /tickets/{id}` y anunciarlas sería ruido.

**Alternativa descartada:** un dominio `global` que dispare todo — más eventos, más refrescos y
ninguna precisión; anunciar todas las mutaciones de compras — eventos sin efecto sobre el pedido.

### D-14 — Interruptor de despliegue con el canal encendido por defecto

El canal se controla con una configuración de entorno (encendido por defecto). Apagado, la
operación responde **503** con un `detail` claro, la aplicación sigue operando como hoy y no se
abre ninguna conexión. No es un permiso ni una capacidad: es una válvula de operación, como el
interruptor del límite de tasa de la 025.

**Por qué:** permite retirar la función de un despliegue sin tocar código ni revertir la feature,
y da una salida si el borde o el bus se comportan mal en producción. La UI no debe romperse: sin
canal, las vistas cargan y se refrescan como antes.

## 5. Reglas del flujo

### 5.1 Ciclo de vida de la conexión

| Estado | Quién lo provoca | Qué se observa | Salida |
|---|---|---|---|
| `sin_sesion` | No hay sesión Clerk o la identidad local no está disponible | No se abre el canal | `conectando` cuando hay identidad |
| `conectando` | Apertura con Bearer | Petición de flujo en curso | `suscrita` al recibir `listo`; 401/403 → `cerrada` sin reintento; 429 → espera `Retry-After`; error de red → retroceso |
| `suscrita` | `listo` recibido | Eventos `cambio`, latidos y `estado` | `renovando`, `degradada` o `cerrada` |
| `renovando` | Vence la credencial o se alcanza la vida máxima de la conexión | El servidor cierra el flujo; el cliente pide token nuevo y reabre; al abrir resincroniza | `suscrita` o `cerrada` si no hay sesión |
| `degradada` | El bus no responde o el suscriptor cae | La conexión sigue abierta con latidos y `estado: degradado`; la app funciona | `suscrita` al recuperarse, con resincronización |
| `cerrada` | Cierre de sesión, salida de la aplicación o cierre de la pestaña (no el cambio de ruta), o 401/403 | No hay más frames ni reintentos | — |

Reglas:

1. **Una conexión por pestaña.** Las vistas se suscriben al hub local; no abren su propio canal.
2. **La conexión no retiene una sesión de base de datos** mientras espera eventos. La identidad,
   la institución, el rol, las capacidades y la expiración se resuelven y se copian en un
   **contexto inmutable** antes de abrir el flujo; las sesiones de control y de negocio se cierran
   **antes** de la espera, y el bucle de eventos no consulta la base ni toma una conexión del
   pool.
3. **Latido** como comentario de flujo al menos cada 25 segundos (configurable), para que los
   proxies no corten por inactividad y el cliente distinga una conexión viva de una colgada.
4. **Renovación** al vencer la credencial o al alcanzar la vida máxima de la conexión (300 s por
   defecto), lo que ocurra primero: el servidor cierra el flujo, el cliente reabre con un token
   vigente y se **reevalúan la institución y las capacidades**. Si el token es muy corto, la
   pestaña no abre más de una conexión cada 30 segundos y espera el siguiente turno.
5. **Reintento** solo ante fallo de red, 5xx o 429: retroceso exponencial con jitter, tope de 30
   segundos entre intentos. Ante 401/403 no se reintenta. Ante 429 se respeta `Retry-After` y
   `X-RateLimit-Reset`.
6. **Sin tormenta**: una caída de dos minutos no produce más de ocho intentos por pestaña ni más
   de dos por minuto después del primer minuto.

### 5.2 Publicación por mutación

Toda mutación confirmada **intenta** publicar, después del commit, con los dominios que su
cambio deja obsoletos. La publicación es best-effort y a lo sumo una vez (D-8). La tabla completa
está en el Anexo A; el resumen es:

| Mutación | Dominios | Por qué |
|---|---|---|
| Alta de pedido | `pedidos` | Aparece una tarjeta y cambia el KPI de activos |
| Edición de pedido | `pedidos` | Cambian asunto, ítems o prioridad en tablero y detalle |
| Aprobación | `pedidos` | Cambia el estado y la columna del tablero |
| Retiro | `pedidos` + `inventario` | Cierra el pedido y rebaja stock; cambian alertas y disponibilidad |
| Confirmación de entrega | `pedidos` | Cambia la etiqueta de proceso a «Entregado» |
| Anulación desde `EnRevision` | `pedidos` | Cambia el estado a `Anulado` |
| Anulación administrativa del retiro | `pedidos` + `inventario` | Devuelve stock y cambia el estado |
| Rechazo | `pedidos` | Cambia el estado a `Anulado` |
| Cambio de estado de legado | `pedidos` | Cambia el estado del pedido |
| Movimiento manual de stock | `inventario` | Cambia existencias, alertas, actividad y disponibilidad |
| Emisión de OC | `compras` (+ `pedidos` si el plan asigna a algún pedido) | Congela la cobertura y cambia la cadena del pedido |
| Facturación de OC | `compras` (+ `pedidos` si la OC pasa a `Facturada` con plan) | La cadena del pedido muestra la OC facturada |
| Cancelación de OC | `compras` (+ `pedidos` si retira una OC `Emitida` con plan) | El pedido vuelve a ser asignable y la cadena cambia |
| Recepción de orden de compra | `inventario` + `compras` (+ `pedidos` si cambia la cadena o desbloquea) | Incrementa stock, cierra la OC y puede cubrir pedidos `EnCurso` |

Reglas:

1. **Nunca antes del commit.** Una mutación que no confirma no publica.
2. **Best-effort con el bus sano.** Toda mutación confirmada **intenta** publicar; Redis Pub/Sub
   no confirma entrega ni persiste, así que un frame perdido es posible. La convergencia no
   depende del evento: cada apertura, foco o resincronización relee. Un duplicado no está
   garantizado; si ocurre, la agrupación lo absorbe.
3. **Cota de publicación.** El intento tiene una espera máxima de **0,5 s**; agotada, el evento se
   descarta y la respuesta ya confirmada sigue su curso. No hay reintento de publicación.
4. **Nunca datos de negocio.** El frame no transporta importes, cantidades, nombres, correos,
   estados ni identificadores; el sobre interno puede llevar metadatos de enrutamiento y nunca se
   serializa.
5. **El actor también recibe el evento.** Su vista puede haberse actualizado con la respuesta de
   la mutación, pero la relectura por evento es la garantía común.

### 5.3 Audiencia y aislamiento

| Dominio | Roles que lo reciben | Condición adicional |
|---|---|---|
| `pedidos` | Administrador y Bodeguero de la institución | Capacidad `tickets` habilitada |
| `pedidos` | Solicitante **dueño del pedido** | Capacidad `tickets` habilitada |
| `inventario` | Administrador, Bodeguero y Solicitante | Capacidad `inventario` habilitada |
| `compras` | Administrador y Bodeguero | Capacidad `compras` habilitada |
| `dashboard` (marca sintética) | Conexiones con la capacidad `dashboard` | Solo si un dominio de origen `pedidos` o `inventario` no es visible; nunca convive con el dominio oculto y su `motivo` es `cambio` |

Reglas:

1. La institución sale **solo de la identidad**; un parámetro de institución, sede o usuario
   enviado por el cliente se ignora.
2. Un rol fuera de la matriz de la operación (Superadmin) no abre el canal: **403**.
3. Un dominio cuya lectura está denegada por capacidad no se entrega, aunque el rol tenga el
   resto de los dominios; si el dominio oculto es `pedidos` o `inventario` y la conexión tiene
   `dashboard`, se sustituye por la marca `dashboard` (AC-28). Si no, no se envía nada.
4. La señal de inventario no se filtra por sede: no lleva sede ni datos y la lectura posterior
   ya está acotada. Se acepta esa actividad agregada dentro de la institución.
5. Ningún frame incluye identificadores de recurso, institución o usuario, ni siquiera para el
   dueño. El sobre interno puede llevar `institucion_id` y `usuario_id` para enrutar; no se
   serializa.
6. **Fan-out al dueño.** Un evento de pedidos dirigido a un Solicitante se entrega solo si su
   `usuario_id` está en la audiencia del sobre. Una recepción o emisión que afecta N pedidos de N
   dueños se publica una vez con el conjunto de dueños y cada conexión recibe como máximo un
   frame **por evento**; no se abre una conexión por dueño.
7. **Orden del filtro.** Primero institución, después audiencia de dueño para `pedidos`, después
   visibilidad por rol y capacidad, y al final la sustitución `dashboard`. Un Solicitante no
   dueño no recibe ni el dominio ni la marca `dashboard` por un pedido ajeno.
8. **Efecto de la competencia entre pedidos.** La disponibilidad derivada de un pedido
   (`stock_disponible`) puede cambiar porque otro pedido de la misma sede se emitió o se retiró,
   no solo porque cambió el stock. El Bodeguero recibe todos los eventos de pedidos y ve el
   estado vigente; el Solicitante, que no recibe pedidos ajenos, puede ver esa etiqueta
   desactualizada hasta su siguiente lectura. Es un dato informativo: la validación real del
   retiro ocurre en el servidor y el Bodeguero es quien actúa sobre ella.

### 5.4 Refresco en el cliente

| Vista | Dominios que la invalidan | Lecturas que repite |
|---|---|---|
| Tablero de pedidos | `pedidos`, `inventario` | Lista de pedidos |
| Detalle del pedido | `pedidos`, `inventario` | Detalle e historial |
| Dashboard | `pedidos`, `inventario`, `dashboard` | Dashboard consolidado |
| Panel de recepciones (fuera de la superficie mínima) | `compras` | Lista de órdenes |

Reglas:

1. Al recibir `listo`, tras cada reapertura y al volver a foco, se resincronizan **todas** las
   vistas activas una vez.
2. Los eventos se agrupan por vista con una ventana de silencio corta (del orden de 250 ms) y un
   máximo de espera de 1 segundo desde el primer evento de la ráfaga: el refresco se lanza
   cuando la ráfaga se detiene, con máximo un refresco en vuelo y, como mucho, uno pendiente.
3. El refresco conserva filtros de periodo y orden del tablero, búsqueda, pestaña activa,
   posición de scroll, diálogos abiertos y texto escrito.
4. Un fallo de refresco no borra los datos ya mostrados ni cierra la vista; se reintenta en la
   siguiente invalidación o resincronización.
5. Una pestaña oculta no refresca; al volver a foco hace una sola resincronización.
6. El refresco no muestra el placeholder de carga inicial, no reinicia scroll, filtros, orden,
   búsqueda, pestaña ni diálogo abierto y no borra el texto escrito.
7. La marca `dashboard` invalida solo el dashboard; no refresca el tablero ni el detalle.

### 5.5 Degradación y recuperación

- **Bus caído:** la API de negocio responde igual; `/ready` sigue midiendo solo la base (025); el
  flujo permanece abierto con latidos y anuncia `degradado`. Al recuperarse anuncia `recuperado`
  y el cliente resincroniza una vez.
- **Canal caído o no soportado:** el cliente reintenta con retroceso; la aplicación sigue
  navegable y operable, y no se activa sondeo.
- **Sesión terminada:** la conexión se cierra, no se reintenta y la aplicación aplica su
  tratamiento habitual de sesión.
- **Capacidad apagada o institución desactivada:** la ventana máxima es la menor entre la
  vigencia del token y `VIDA_MAXIMA_CONEXION_SEGUNDOS` (300 s por defecto), lo que ocurra
  primero. En la siguiente reapertura se reevalúan la institución y las capacidades: el `listo`
  deja de incluir el dominio apagado, la lectura pasa a 403 o la identidad deja de resolver con
  401. Una conexión abierta no entrega eventos nuevos de un dominio que ya no puede ver más allá
  de esa ventana (AC-31).

### 5.6 Invariantes

1. Ningún evento se publica antes del commit de la mutación que lo origina.
2. Con el bus sano, toda mutación confirmada del Anexo A **intenta** publicar; la entrega es
   best-effort y no garantizada. La convergencia es por relectura.
3. Ningún frame cruza instituciones ni llega a un rol o dominio sin acceso; el sobre interno no
   se serializa y el frame no lleva identificadores.
4. Ningún frame transporta datos de negocio ni identificadores de recurso, institución o usuario.
5. Toda apertura o reapertura resincroniza; no hay reproducción de eventos.
6. La disponibilidad y el resultado de la API de negocio no dependen del bus.
7. Hay como máximo una conexión por pestaña y una relectura en vuelo por vista.
8. La conexión no retiene una sesión del pool de base de datos.
9. La credencial viaja solo en la cabecera `Authorization`.
10. La institución y las capacidades se reevalúan a más tardar en la reapertura de la conexión
    (≤ 300 s o la vigencia del token, lo que ocurra primero).
11. La feature no cambia el modelo de datos, la versión de esquema ni las reglas de negocio.

## 6. Contrato de la API

### 6.1 `GET /api/v1/eventos/`

- **Método y ruta:** `GET /api/v1/eventos/`, con barra final canónica para evitar la redirección
  de FastAPI en una conexión de larga duración.
- **Autenticación:** `Authorization: Bearer <token de sesión de Clerk>`. Sin sesión o con token
  inválido o vencido: **401**, igual que el resto de `/api/v1`. Rol fuera de la matriz:
  **403**. Canal deshabilitado: **503**. Límite de tasa: **429** con `Retry-After`.
- **Petición:** sin cuerpo y sin parámetros de ámbito. No existe `?institucion_id`, `?sede_id`,
  `?usuario_id` ni `?dominios`; cualquier intento de ampliar el ámbito se ignora.
- **Éxito:** **200** con `Content-Type: text/event-stream; charset=utf-8`,
  `Cache-Control: no-store` y una indicación al proxy de no almacenar en búfer
  (`X-Accel-Buffering: no`). La respuesta permanece abierta hasta el cierre por vencimiento,
  cierre de sesión, error o apagado del servidor.
- **Operación de solo lectura:** no muta datos ni tiene efectos de negocio; repetir la apertura
  no cambia el estado, aunque cada apertura resincroniza las vistas activas.

**Frames del flujo.** Todos los frames son de texto y terminan en una línea vacía. El cliente
ignora los tipos que no conozca.

| Frame | Cuándo | `data` | Efecto en el cliente |
|---|---|---|---|
| `listo` | La suscripción quedó activa | `{"dominios": ["pedidos","inventario"]}` (incluye `dashboard` si la capacidad está encendida) | Resincronizar las vistas activas una vez |
| `cambio` | Una mutación confirmada del Anexo A | `{"dominios": ["pedidos"], "motivo": "retiro"}` | Invalidar las vistas interesadas y agrupar |
| `estado` | El bus se degrada o se recupera | `{"estado": "degradado"}` o `{"estado": "recuperado"}` | No bloquear la app; al recuperarse, resincronizar una vez |
| Latido | Cada ≤ 25 s | Línea de comentario `: latido` | Ninguno; mantiene viva la conexión |

Ejemplo de frame de cambio:

```text
event: cambio
data: {"dominios": ["pedidos", "inventario"], "motivo": "retiro"}

```

Ejemplo de frame sintético para una conexión con `dashboard` pero sin acceso a `pedidos`:

```text
event: cambio
data: {"dominios": ["dashboard"], "motivo": "cambio"}

```

Reglas del contrato:

1. **Sin `id:` y sin `retry:`.** El servidor no emite identificadores de evento ni delega en el
   navegador la política de reintento; la controla el cliente. Un `Last-Event-ID` entrante se
   ignora.
2. **Sin datos de negocio.** Los únicos valores posibles de `dominios` son `pedidos`,
   `inventario`, `compras` y la marca sintética `dashboard`. El `motivo` es un literal de
   diagnóstico (`alta`, `edicion`, `aprobacion`, `retiro`, `confirmacion_entrega`, `anulacion`,
   `rechazo`, `cambio_estado`, `movimiento`, `recepcion`, `emision_oc`, `facturacion_oc`,
   `cancelacion_oc`, `cambio`) y no se presenta como notificación. Cuando la marca `dashboard`
   sustituye a un dominio oculto, el `motivo` es siempre `cambio`: no se filtra el motivo real.
   Si la marca convive con un dominio visible en el mismo frame, el `motivo` también se normaliza
   a `cambio`.
3. **Sin identificadores en el frame.** El frame no contiene `institucion_id`, `usuario_id` ni
   ids de pedido, producto u orden, aunque el sobre interno los use para enrutar. El sobre nunca
   se serializa.
4. **Los errores previos al flujo** (401, 403, 429, 503) son JSON con `detail`, como el resto de
   la API. Una vez abierto el flujo, un error interno cierra la conexión; no se envía un frame de
   error con datos internos.
5. **El cierre por vencimiento no es un error de negocio:** el cliente lo trata como renovación.

### 6.2 Documentación OpenAPI y excepción de `response_model`

La operación se publica en `/openapi.json` con:

- `summary` y `description` que explican el flujo, el aislamiento, el ciclo de vida y la
  excepción de `response_model`.
- `status_code=200` y `response_class` de flujo con media type `text/event-stream`.
- Respuestas documentadas **200**, **401**, **403**, **429** y **503**.
- El formato de `listo`, `cambio`, `estado` y latido descrito en la descripción, con los valores
  cerrados de `dominios` y `motivo`.

**No declara `response_model` JSON** porque el cuerpo no es un documento JSON. Esta es la
excepción explícita a `AGENTS.md` §6: la ruta queda documentada y con contrato, sin un esquema de
respuesta incompatible. La matriz central la registra como una operación más.

### 6.3 Gobierno: matriz y capacidades

- Se añade **una sola** operación a `MATRIZ_PERMISOS`: `GET /api/v1/eventos/` con
  `{Administrador, Bodeguero, Solicitante}`. La matriz pasa de **72 a 73** operaciones; las 72
  previas conservan exactamente sus roles y ninguna se retira.
- `/openapi.json` pasa de **74 a 75** entradas (73 de v1 + `GET /` + `/health`). Las aserciones
  absolutas existentes de la 024/025/013/012 deben ampliarse explícitamente, no relajarse.
- La operación **no** se asocia a una capacidad en el mapa de capacidades: la disponibilidad por
  dominio se resuelve por evento (D-4) y la marca `dashboard` usa la capacidad `dashboard` ya
  existente. El conjunto cerrado de **siete** capacidades no cambia.
- No se crea un rol, un permiso implícito ni una operación de escritura.

## 7. Criterios de aceptación

### Transporte y contrato

- [x] **AC-1** DADO una sesión válida de Administrador, Bodeguero o Solicitante, CUANDO abre
      `GET /api/v1/eventos/`, ENTONCES recibe **200** con `Content-Type: text/event-stream`, un
      frame `listo` con los dominios que le corresponden y la conexión permanece abierta sin que
      el cliente sondee. La respuesta declara `Cache-Control: no-store`.
  - **Verificación prevista:** test de contrato con el cliente de pruebas; lectura de cabeceras y
    del primer frame; recorrido en 4200.
  - **Evidencia:** `test_eventos_endpoint_028.py::test_sesion_valida_abre_el_flujo_con_listo_y_sus_cabeceras`
      (200, `text/event-stream; charset=utf-8`, `Cache-Control: no-store`, `listo`); gated
      `test_pool_tiempo_real_028.py::test_eventos_abre_para_identidad_de_tenant_postgres_ac_1`;
      `tiempo-real.service.spec.ts` (fetch con `Accept: text/event-stream`).
- [x] **AC-2** SI la petición no lleva `Authorization`, o el token es inválido o vencido,
      ENTONCES responde **401** con el mismo cuerpo que el resto de `/api/v1`. SI el rol es
      Superadmin, ENTONCES **403** por matriz. SI el token viaja solo en la URL o en una cookie,
      ENTONCES no autentica y responde **401**.
  - **Verificación prevista:** tests de seguridad parametrizados por rol y por ubicación de la
    credencial; comprobación de que ningún parámetro de ámbito altera la respuesta.
  - **Evidencia:** `test_permisos_endpoint_028.py::test_token_en_url_o_cookie_no_autentica` (token en query y
      cookie → 401, mismo cuerpo que sin credencial), `::test_sin_authorization_responde_401`,
      `::test_superadmin_recibe_403_por_matriz_sin_suscribirse`;
      `test_contexto_tiempo_real_028.py` (403 sin institución).
- [x] **AC-3** DADO un token emitido con una expiración conocida (por ejemplo, con la costura
      `firmar_token` de la suite de autenticación), CUANDO el flujo se abre, ENTONCES el servidor
      lo cierra en **`exp - 10 s`** (margen de reloj) y el cliente reabre con un token vigente y
      resincroniza sin intervención del usuario. La expiración se toma del token validado, no de
      un TTL fijo. DADO que la sesión se cierra, ENTONCES no se entrega ningún evento más y el
      cliente no reintenta.
  - **Verificación prevista:** test con la costura de firma/JWKS de `test_auth.py` y un `exp`
    corto; prueba manual de cierre de sesión en 4200.
  - **Evidencia:** `test_eventos_endpoint_028.py::test_el_flujo_se_cierra_en_exp_menos_el_margen`;
      `test_auth.py::test_resolver_identidad_copia_el_exp_del_token_validado`;
      `test_contexto_tiempo_real_028.py::test_identidad_construida_sin_expira_en_conserva_el_default`;
      `tiempo-real.service.spec.ts` (reapertura y mínimo entre aperturas).
- [x] **AC-4** El flujo emite un latido con la cadencia configurada (por defecto 25 segundos y
      nunca superior a 30) y atraviesa el proxy de desarrollo y el borde nginx sin
      almacenamiento en búfer ni corte por inactividad; la consola no muestra errores de
      conexión.
  - **Verificación prevista:** test con intervalo de latido acotado; recorrido de 60 s en 4200 y
    en 8080 con inspección de red.
  - **Evidencia:** `test_eventos_endpoint_028.py::test_emite_al_menos_un_latido_con_el_intervalo_corto`; T0
      (proxy de desarrollo: `listo` 268 ms, latidos ~2 s, sin `content-encoding`); T21 (nginx:
      primer paquete `listo`, latido 1 s, chunked, sin `Content-Encoding`); humo 8080 de T23. La
      prueba de 60 s y la consola no se midieron (excepción aceptada).

### Publicación

- [x] **AC-5** DADO el bus sano y la suscripción activa, CUANDO se ejecuta cualquiera de las
      mutaciones de pedidos del Anexo A —alta, edición, aprobación, retiro, confirmación de
      entrega, anulación desde `EnRevision`, anulación administrativa del retiro, rechazo y cambio
      de estado de legado—, ENTONCES una sesión autorizada de la misma institución recibe un frame
      `cambio` con el dominio `pedidos` (y `inventario` cuando la mutación mueve stock) en **5
      segundos o menos**.
  - **Verificación prevista:** test de integración parametrizado por mutación con un cliente de
    flujo; recorrido manual de cada acción con dos sesiones.
  - **Evidencia:** `test_publicacion_tickets_028.py` (alta, edición, aprobación, confirmación, `PATCH`,
      anulación y rechazo) y `test_publicacion_retiro_028.py` (retiro y anulación desde
      `Cerrado`), con el bus falso y la publicación después del commit; recorrido manual
      AC-9/AC-10/AC-11.
- [x] **AC-6** CUANDO se registra un movimiento manual de stock, ENTONCES se anuncia
      `inventario`. CUANDO se recepciona una orden de compra, ENTONCES se anuncian `inventario` y
      `compras` y, si la recepción cambia la cadena de algún pedido o desbloquea pedidos
      `EnCurso`, también `pedidos`. El detalle del pedido pasa a mostrar disponibilidad y la
      acción de retiro sin recargar.
  - **Verificación prevista:** test de recepción con dos pedidos, uno cubierto y otro no;
    recorrido con la OC de la semilla; comprobación del badge y del botón en el detalle.
  - **Evidencia:** `test_publicacion_inventario_028.py` (movimiento → `inventario`);
      `test_publicacion_recepcion_028.py` (recepción → `inventario`+`compras`±`pedidos` y
      `test_detalle_del_bodeguero_refleja_stock_disponible_tras_la_recepcion`); manual AC-13.
- [x] **AC-7** SI una mutación responde 401, 403, 404, 409 o 422, o revierte por un fallo interno,
      ENTONCES no publica ningún evento. SI una mutación confirma **y el bus está sano**, ENTONCES
      intenta publicar y, en la prueba con el bus sano y la suscripción activa, se observa el
      frame. La entrega es best-effort: la prueba no exige que toda mutación confirmada llegue
      siempre, y un duplicado no está garantizado.
  - **Verificación prevista:** tests de mutaciones rechazadas (retiro sin stock, anulación de un
    confirmado, rechazo desde `EnCurso`), de una mutación forzada a revertir y de una mutación
    confirmada con el bus sano; conteo de frames y comprobación de que el rechazo no publica.
  - **Evidencia:** `test_publicacion_*_028.py`: 404/409/422, rollback forzado, doble envío 409 y
      `test_el_bus_caido_no_cambia_el_status_ni_el_cuerpo`;
      `test_la_publicacion_*_ocurre_despues_del_commit`; conteo de sobres en retiro y recepción.
- [x] **AC-8** DADO que el bus deja de responder, CUANDO se ejecuta una mutación, ENTONCES la
      respuesta conserva su status y su cuerpo habituales, su latencia no supera la habitual en
      más de **0,5 s**, `/ready` sigue en **200**, no se entrega ningún frame `cambio` y el flujo
      permanece abierto y anuncia `estado: degradado`. CUANDO el bus vuelve, ENTONCES anuncia
      `recuperado`, los eventos nuevos llegan sin reiniciar la aplicación y la línea de log
      estructurada registra apertura, degradación y recuperación sin token, correo, query ni
      datos de negocio.
  - **Verificación prevista:** test con un bus simulado que falla o que cuelga la respuesta;
    medición de latencia con el bus colgado; gated con Redis detenido; inspección de la línea de
    log estructurada.
  - **Evidencia:** `test_eventos_degradacion_028.py` (degradado/recuperado sin cerrar HTTP, retroceso
      1/2/4/8/10, mutación con bus colgado dentro de la cota, `/ready` 200 y log sin PII);
      `test_almacen_eventos_028.py` (cota 0,5 s); gated
      `test_bus_eventos_redis_028.py::test_redis_detenido_conserva_la_respuesta_y_ready_200`.

### Propagación observable

- [x] **AC-9** DADOS un **Solicitante** y un usuario con acceso al tablero completo
      (**Administrador/Bodeguero**) de la misma institución, con el tablero abierto en ambos,
      CUANDO el **Solicitante crea un pedido** —único rol habilitado para el alta desde la
      enmienda de la 007—, ENTONCES el Administrador/Bodeguero ve la tarjeta en su columna sin
      recargar la página ni pulsar nada, en **5 segundos o menos**. Para un Solicitante no dueño
      aplica AC-16.
  - **Verificación prevista:** dos sesiones reales (Solicitante creador y Administrador o
    Bodeguero observador) en 4200 y 8080; captura de la tarjeta nueva.
  - **Evidencia:** `tickets.component.spec.ts` (frame `pedidos` → una recarga silenciosa, tarjeta sin
      recargar) y `test_publicacion_tickets_028.py::test_alta_confirmada_publica_pedidos_con_motivo_alta`;
      recorrido manual del 28/Nov/2026 (Solicitante crea; Administrador ve la tarjeta en segundos).
- [x] **AC-10** CUANDO el Administrador aprueba un pedido, ENTONCES el Bodeguero ve la tarjeta
      pasar a `EnCurso`; CUANDO el Bodeguero registra el retiro, ENTONCES el Solicitante ve el
      pedido `Cerrado` y la acción de confirmar entrega, y el Administrador lo ve en
      «Terminados»; CUANDO el Solicitante confirma, ENTONCES el Administrador ve «Entregado»;
      CUANDO se anula o rechaza, ENTONCES todos los autorizados ven `Anulado`. Todo sin recargar.
  - **Verificación prevista:** recorrido de los cuatro caminos con dos o tres sesiones; tests de
    integración de frames por transición.
  - **Evidencia:** Frames por transición en `test_publicacion_tickets_028.py` (aprobación, confirmación,
      anulación, rechazo) y `test_publicacion_retiro_028.py` (retiro); specs de tablero y detalle;
      recorrido manual del 28/Nov/2026 (aprobación → retiro → confirmación → «Entregado»).
- [x] **AC-11** CUANDO el Solicitante o el Administrador editan un pedido en `EnRevision`,
      ENTONCES el tablero y el detalle de las otras sesiones autorizadas —Administrador,
      Bodeguero y el Solicitante dueño— muestran el asunto, los ítems o la prioridad nuevos sin
      recargar. Un Solicitante no dueño no se actualiza (AC-16).
  - **Verificación prevista:** edición real en 4200 con dos sesiones; test de frame `pedidos`.
  - **Evidencia:** `test_publicacion_tickets_028.py::test_edicion_confirmada_publica_pedidos_con_motivo_edicion`;
      specs de tablero y detalle; recorrido manual del 28/Nov/2026 (prioridad Media → Alta vista
      al momento por el Administrador).
- [x] **AC-12** CUANDO cambia un pedido, un movimiento de stock, una recepción o una mutación de
      OC que toca la cadena del pedido, ENTONCES el dashboard de otro usuario autorizado
      (Administrador/Bodeguero; para el Solicitante, solo sus propios pedidos, ver AC-16)
      actualiza el KPI de pedidos activos, el de unidades en stock, el log de alertas y la
      actividad reciente que correspondan, sin recargar y conservando el ámbito del rol (el
      Solicitante sigue sin actividad).
  - **Verificación prevista:** dashboard abierto en dos sesiones con los tres roles; comparación
    antes/después de cada mutación; test de relectura del DTO.
  - **Evidencia:** `dashboard.component.spec.ts` (frame `pedidos`/`inventario`/`dashboard` → un GET, sin
      placeholder, conserva datos, Solicitante sin actividad) y publicación de las mutaciones que
      lo invalidan; recorrido manual del 28/Nov/2026 (KPI y actividad en unos segundos, ≤5 s).
- [x] **AC-13** DADO un pedido `EnCurso` sin stock y una recepción que lo cubre, CUANDO la
      recepción confirma, ENTONCES el detalle del Bodeguero muestra `stock_disponible = true` y
      la acción «Registrar retiro» sin recargar, y el Solicitante ve actualizada la etiqueta de
      proceso.
  - **Verificación prevista:** recorrido con la OC y el pedido de la semilla; verificación de la
    fila de desbloqueo en el historial.
  - **Evidencia:** `test_publicacion_recepcion_028.py::test_detalle_del_bodeguero_refleja_stock_disponible_tras_la_recepcion`;
      `ticket-detalle.component.spec.ts`; recorrido manual del 28/Nov/2026 (OC emitida/facturada y
      recepcionada → `stock_disponible = true` y «Registrar retiro»).
- [x] **AC-14** El refresco por evento conserva el periodo y el orden del tablero, la búsqueda, la
      pestaña activa, la **posición de scroll** y el texto escrito en un diálogo abierto; **no
      muestra el placeholder de carga inicial** ni reinicia ninguno de esos estados. SI el
      refresco falla, ENTONCES los datos previos permanecen visibles.
  - **Verificación prevista:** specs de tablero y detalle con un evento simulado, scroll y un
    diálogo abierto; recorrido manual con el filtro de periodo y la búsqueda activos.
  - **Evidencia:** `tickets.component.spec.ts` (periodo, orden, búsqueda y scroll),
      `ticket-detalle.component.spec.ts` (diálogo y motivo escritos) y
      `refresco-agrupado.spec.ts` (ráfaga, uno en vuelo, uno pendiente); recorrido manual del
      28/Nov/2026 con filtros y diálogo abiertos.

### Aislamiento

- [x] **AC-15** DADAS dos instituciones con sesiones abiertas, CUANDO se muta un pedido, un
      movimiento o una recepción en una, ENTONCES la sesión de la otra **no recibe ningún frame
      `cambio` de esa mutación** (el `listo` propio de su apertura es independiente) ni cambia
      ninguna vista. Un parámetro de institución enviado por el cliente no altera la suscripción.
  - **Verificación prevista:** test con dos identidades de instituciones distintas y el mismo
    bus; recorrido con dos navegadores; comprobación de que el frame no llega.
  - **Evidencia:** `test_eventos_filtro_028.py::test_la_institucion_ajena_no_recibe_el_sobre_de_otra_institucion`;
      `test_filtro_eventos_028.py::test_sobre_de_otra_institucion_se_descarta_aunque_el_dominio_sea_visible`;
      `test_tiempo_real_028.py::test_un_correo_sin_mapa_de_control_no_abre_el_flujo_ac_15`;
      parámetros de ámbito ignorados.
- [x] **AC-16** DADOS dos Solicitantes de la misma institución, CUANDO uno crea, edita o anula un
      pedido propio, ENTONCES el otro **no recibe el frame `pedidos` ni la marca `dashboard`** por
      ese pedido ajeno, y su tablero no refresca por él; el Administrador y el Bodeguero sí lo
      reciben. Puede recibir `inventario` si la mutación mueve stock (retiro o anulación con
      devolución), conforme a §5.3 regla 4, sin que eso revele la existencia del pedido. Ningún
      frame revela la existencia del pedido del otro.
  - **Verificación prevista:** test con dos Solicitantes y conteo de frames por conexión;
    recorrido con dos sesiones.
  - **Evidencia:** `test_eventos_filtro_028.py` (dueño recibe; otro Solicitante no recibe ni la marca;
      Administrador y Bodeguero sí) y `test_filtro_eventos_028.py` (misma matriz a nivel de filtro).
- [x] **AC-17** SI un rol no tiene acceso a un dominio (por ejemplo, un Solicitante en `compras`),
      ENTONCES no recibe frames de ese dominio. SI la capacidad del dominio está apagada,
      ENTONCES el dominio no aparece en el frame; si el dominio oculto es `pedidos` o
      `inventario` y la conexión tiene la capacidad `dashboard`, se entrega la marca `dashboard`
      (AC-28), sin nombrar el dominio oculto. El Superadmin no abre el canal (403).
  - **Verificación prevista:** tests con instituciones de capacidades apagadas y por rol; matriz
    de frames esperados.
  - **Evidencia:** `test_filtro_eventos_028.py` (capacidad apagada oculta el dominio; `compras` no sintetiza
      marca; sin `dashboard` no hay frame); `test_eventos_filtro_028.py`;
      `test_permisos_endpoint_028.py` (Superadmin 403).
- [x] **AC-18** Ningún frame contiene asunto, cantidades, estado, nombre, correo, stock,
      institución ni identificadores de pedido, producto, orden o usuario; solo `dominios`,
      `motivo` y `estado`. La marca `dashboard` es el único valor sintético y no revela el
      dominio de origen. Los logs del canal no incluyen token, correo ni datos de negocio.
  - **Verificación prevista:** inspección de frames en los tests de integración y de los logs de
    una sesión real.
  - **Evidencia:** `test_eventos_endpoint_028.py::test_el_frame_listo_no_lleva_identificadores_ni_el_flujo_usa_id_o_retry`;
      `test_filtro_eventos_028.py::test_el_frame_serializado_no_lleva_ids_ni_institucion_ni_usuario`;
      `test_eventos_degradacion_028.py::test_la_linea_tiempo_real_registra_campos_permitidos_sin_pii`.

### Resiliencia y límites

- [x] **AC-19** SI se pierde la red o el servidor se reinicia, ENTONCES el cliente reintenta con
      retroceso exponencial y jitter, la aplicación sigue navegable y, al reconectar, las vistas
      activas se resincronizan y muestran los cambios ocurridos durante la caída sin recargar la
      página.
  - **Verificación prevista:** prueba con el backend detenido y reiniciado; cambios hechos
    mientras la pestaña estaba desconectada; test del planificador de reintentos.
  - **Evidencia:** `tiempo-real.service.spec.ts` (401/403 sin reintento, 429 con `Retry-After`, 5xx/red con
      backoff y jitter, una sola conexión; `listo`/`recuperado` resincronizan).
- [x] **AC-20** DADAS 20 mutaciones en un segundo (una ráfaga sin silencio), ENTONCES cada vista
      activa hace como máximo dos lecturas (agrupación), no veinte. DADA una caída de dos
      minutos, ENTONCES una pestaña no supera ocho intentos de reconexión y, después del primer
      minuto, no más de dos por minuto. Ante un 429 no se reintenta antes de `Retry-After`.
  - **Verificación prevista:** test del agrupador y del planificador; conteo de peticiones en el
    navegador con la red simulada.
  - **Evidencia:** `refresco-agrupado.spec.ts` (20 solicitudes → 1 ejecución; máximo 1 s; uno en vuelo;
      `cancelar`) y `tiempo-real.service.spec.ts` (tope 30 s, mínimo 30 s entre aperturas,
      `Retry-After`).
- [x] **AC-21** Con el límite de tasa activo, **2–3 sesiones bajo la misma IP** con el canal abierto
      durante **3 minutos** no reciben **429** (**0×429**). La apertura del canal cuenta como una
      petición; cada sesión reabre una vez por renovación, no en bucle; con tokens de ~60 s y el
      cierre en `exp - 10 s` (~50 s) más el mínimo de 30 s entre aperturas, la ventana real produce
      **4–5 aperturas por sesión** en 3 minutos. `X-RateLimit-Remaining` sigue **> 0** al final y
      las renovaciones no agotan las 120 por minuto.
  - **Verificación prevista:** recorrido de 3 minutos en 8080 con el limitador encendido;
    inspección de `X-RateLimit-Remaining`, del número de aperturas (4–5 con token de ~60 s) y de
    la ausencia de 429 (0×429); prueba con token de vigencia corta.
  - **Evidencia:** `tiempo-real.service.spec.ts` (una apertura y mínimo entre aperturas); T14/T15 (hub y
      ventana de renovación con cierre en `exp - 10 s`); T21 (ráfaga de 60 en 8080: 20×401 +
      40×429; el 429 conserva JSON y CORS). Precisión aprobada: 4–5 aperturas por sesión en
      3 min y 0×429.
- [x] **AC-22** DADA una pestaña oculta, ENTONCES no realiza refrescos mientras permanece oculta y,
      al volver a foco, realiza una sola resincronización. No se abre una segunda conexión para
      la misma pestaña.
  - **Verificación prevista:** spec del hub con `visibilitychange` simulado; inspección de red en
    el navegador.
  - **Evidencia:** `tiempo-real.service.spec.ts` (`document.hidden` no refresca; `visibilitychange` → una
      resincronización; no abre segunda conexión) y `app.component.spec.ts` (una sola conexión
      al navegar).
- [x] **AC-23** DADOS **dos procesos reales del backend** (por ejemplo, `uvicorn --workers 2` o dos
      instancias) que comparten el bus, CUANDO una mutación ocurre en uno, ENTONCES una sesión
      conectada al otro recibe el aviso. La prueba automatizada usa hubs aislados por aplicación
      (no módulos/globales compartidos en el mismo proceso) y la evidencia principal es el
      recorrido manual con dos workers.
  - **Verificación prevista:** test gated con dos aplicaciones y Redis; recorrido manual con dos
    workers en local.
  - **Evidencia:** Gated `test_bus_eventos_redis_028.py::test_dos_instancias_aisladas_comparten_el_bus_y_el_cambio_cruza_redis`
      (**4 passed**, `PUBSUB NUMSUB` confirma el suscriptor). El manual de dos workers no se
      ejecutó (excepción aceptada).

### Gobierno, no regresión y cierre

- [x] **AC-24** `GET /api/v1/eventos/` aparece en `/openapi.json` con su media type, sus respuestas
      200/401/403/429/503 y la descripción de frames, sin `response_model` JSON y con la excepción
      documentada. La matriz pasa de **72 a 73** y `/openapi.json` de **74 a 75**; las aserciones
      absolutas se actualizan de forma explícita.
  - **Verificación prevista:** lectura de `/openapi.json`; tests de cardinalidad; grep de las
      aserciones 72/74 en la suite.
  - **Evidencia:** `test_permisos_endpoint_028.py::test_openapi_publica_la_operacion_sin_response_model_y_con_sus_respuestas`,
      `::test_openapi_y_matriz_suman_una_operacion`,
      `::test_la_matriz_declara_el_canal_para_los_tres_roles_institucionales`; aserciones
      absolutas de `test_contrato_024.py` y `test_permisos_retiro_013.py` en **75/73**.
- [x] **AC-25** La feature no cambia el DDL, la versión de esquema (`026.1`), las 25/22 tablas ni
      las 21 entidades; no añade dependencias; las suites de backend y frontend siguen verdes y
      `ng build` compila sin errores.
  - **Verificación prevista:** gated de instalación limpia; `pip freeze` y `package.json` sin
      cambios; suites completas.
  - **Evidencia:** Suites: SQLite **2323/135/0** (2322 + test AC-2), gated **4+4+4**, `ng test` **758 SUCCESS**,
      `ng build` limpio (`main-UJT3LSFR.js`, 348,36 kB); sin cambios en `database/`, modelos,
      `requirements.txt` ni `package.json`; token `026.1`, 25/22 tablas y 21 entidades.
- [x] **AC-26** El recorrido funcional se completa en **4200** con dos o tres sesiones y escritura
      real, y el humo en **8080** tras reconstruir la imagen confirma el canal a través de nginx.
      La evidencia queda registrada y `roadmap.md`, `MEMORY.md`, `stack.md` y
      `deuda-tecnica.md` quedan sincronizados.
  - **Verificación prevista:** recorrido y capturas; build de la imagen; grep de coherencia
      documental.
  - **Evidencia:** Recorrido manual del usuario del 28/Nov/2026 en **4200** (AC-9/10/11/12/13/14) y humo en
      **8080** tras el rebuild de T21 (imagen `3974188a383e`); documentación sincronizada. Sin
      capturas nuevas (excepción aceptada).

### Correcciones de la clarificación QA (28/Nov/2026)

- [x] **AC-27 (B1) — Sobre interno y fan-out al dueño.** DADO un evento de pedidos con audiencia
      de dueños en el sobre interno, CUANDO se entrega, ENTONCES el frame **no contiene
      `institucion_id`, `usuario_id` ni ids de pedido**, el Solicitante dueño correcto recibe el
      frame, otro Solicitante de la misma institución no lo recibe y el Administrador y el
      Bodeguero sí. Una recepción que desbloquea dos pedidos de dos dueños produce **un** mensaje
      interno con el conjunto de dueños y, como máximo, un frame por conexión.
  - **Verificación prevista:** test de integración con dos dueños y un tercer Solicitante;
    inspección del frame serializado; prueba de la recepción con dos pedidos cubiertos.
  - **Evidencia:** `test_publicacion_recepcion_028.py::test_recepcion_con_plan_y_desbloqueo_publica_un_sobre_con_la_union`;
      `test_publicacion_retiro_028.py::test_el_retiro_publica_un_solo_sobre_y_el_frame_no_lleva_ids`;
      `test_evento_service_028.py` (audiencia y dueños únicos); `test_filtro_eventos_028.py`.
- [x] **AC-28 (M5) — Marca sintética `dashboard`.** DADA una conexión con la capacidad `dashboard`
      encendida pero sin acceso al dominio que cambió (`tickets` o `inventario` apagados),
      CUANDO se muta un pedido o el stock, ENTONCES recibe un frame `cambio` con
      `dominios: ["dashboard"]` y `motivo: "cambio"`, sin el nombre ni el motivo del dominio
      oculto, y el dashboard se refresca. Una conexión sin `dashboard` no recibe la marca; una
      conexión que sí ve el dominio de origen recibe el dominio, no la marca.
  - **Verificación prevista:** test con capacidades encendidas/apagadas; inspección del frame;
    relectura del dashboard en el cliente.
  - **Evidencia:** `test_eventos_filtro_028.py::test_tickets_apagado_entrega_solo_la_marca_dashboard_sin_el_motivo_real`,
      `::test_inventario_apagado_entrega_la_marca_dashboard`,
      `::test_pedidos_e_inventario_apagados_producen_un_solo_frame_dashboard`;
      `test_filtro_eventos_028.py` (sin `dashboard` no hay frame); `dashboard.component.spec.ts`.
- [x] **AC-29 (M6) — Sin retención del pool.** DADO un pool de base de datos pequeño y varias
      conexiones SSE ociosas, CUANDO se ejecutan peticiones de negocio, ENTONCES responden con su
      status habitual y el pool no se agota. La identidad, la institución, el rol, las capacidades
      y la expiración se resolvieron antes de la espera y las sesiones se cerraron.
  - **Verificación prevista:** gated PostgreSQL con pool pequeño y N flujos ociosos; peticiones
    concurrentes; inspección de las conexiones en uso.
  - **Evidencia:** Gated `test_pool_tiempo_real_028.py::test_cinco_flujos_ociosos_no_agotan_el_pool_ac_29`
      (pool 2/0/2 s, 5 flujos ociosos, `GET /tickets/` 200 sin `QueuePool limit`);
      `test_contexto_tiempo_real_028.py::test_contexto_cierra_la_sesion_antes_de_retornar`.
- [x] **AC-30 (M8) — Compras que cambian la cadena del pedido.** CUANDO se emite una OC con plan
      que asigna a algún pedido, se factura una OC que pasa a `Facturada` con plan, se cancela una
      OC `Emitida` con plan o se recepciona una OC que cambia la cadena o desbloquea, ENTONCES se
      anuncia `compras` a Administrador/Bodeguero y `pedidos` a Administrador/Bodeguero y a los
      dueños afectados; `GET /tickets/{id}` refleja el cambio de cadena. Una emisión o cancelación
      sin plan anuncia **solo** `compras`. El alta/edición en `Borrador`, los proveedores y el
      preview **no** publican.
  - **Verificación prevista:** test por mutación con plan con y sin pedidos; lectura del detalle
    antes/después; inspección de frames; grep de las rutas que no publican.
  - **Evidencia:** `test_publicacion_compras_028.py` (emisión, facturación y cancelación con y sin plan;
      corrección de facturada; alta/edición/proveedores/preview no publican);
      `test_publicacion_recepcion_028.py`.
- [x] **AC-31 (M9) — Ventana de capacidades e institución.** DADA una conexión abierta, CUANDO se
      apaga una capacidad o se desactiva la institución, ENTONCES no se entregan eventos del
      dominio afectado más allá de la ventana declarada (la menor entre la vigencia del token y
      300 s); en la siguiente reapertura el `listo` ya no incluye el dominio, la lectura responde
      403 o la identidad responde 401, y el cliente no recibe el dominio oculto.
  - **Verificación prevista:** test con capacidad apagada e institución desactivada y ventana
      corta; gated PostgreSQL; recorrido manual.
  - **Evidencia:** `test_tiempo_real_028.py::test_la_conexion_vieja_entrega_antes_de_la_ventana_y_cierra_al_vencer_ac_31`,
      `::test_la_reapertura_no_incluye_el_dominio_apagado_y_la_lectura_responde_403_ac_31`,
      `::test_la_reapertura_con_la_institucion_inactiva_responde_401_ac_31`.
- [x] **AC-32 (m11) — Interruptor de canal.** DADO el canal deshabilitado por configuración y una
      sesión válida, CUANDO se abre `GET /api/v1/eventos/`, ENTONCES responde **503** con
      `detail`, no se abre ningún flujo, las vistas cargan y las mutaciones responden con
      normalidad; al reactivarlo, el canal vuelve a abrirse.
  - **Verificación prevista:** test con la configuración apagada; comprobación de que no se
      consume una conexión; recorrido de la app sin canal.
  - **Evidencia:** `test_eventos_028.py` (default `True` y validadores de rango);
      `test_permisos_endpoint_028.py::test_canal_apagado_responde_503_sin_abrir_el_flujo`;
      `tiempo-real.service.spec.ts` (401/403 no reintenta) y las vistas cargan por sus GET sin
      depender del canal.

## 8. Restricciones

- **Sin DDL ni modelo nuevo.** No hay tablas, columnas, índices, entidades, migraciones ni
  cambio de token: `026.1`, 25/22 tablas y 21 entidades.
- **Sin dependencias nuevas.** El backend ya tiene el **cliente** `redis==8.1.0`; el **servidor**
  del Compose es `redis:7.2-alpine`. El frontend usa APIs nativas. Una dependencia adicional
  exigiría justificación y verificación previas.
- **Clerk sigue siendo la única autoridad.** No se crea login, cookie de sesión, JWT local,
  ticket de canal ni credencial alternativa.
- **La credencial nunca viaja en la URL, el cuerpo ni una cookie.** Solo en `Authorization`.
- **La conexión no retiene una sesión del pool de base de datos** durante la espera: identidad,
  institución, rol, capacidades y expiración se copian antes de abrir el flujo y las sesiones se
  cierran antes de la espera.
- **Una conexión por pestaña.** No se abre un canal por vista ni por componente.
- **El frame no transporta datos de negocio ni identificadores de recurso, institución o
  usuario.** El sobre interno del bus puede llevar metadatos de enrutamiento y nunca se
  serializa.
- **La marca `dashboard` no crea una capacidad nueva** ni revela el dominio de origen; usa la
  capacidad `dashboard` existente y `motivo: "cambio"`.
- **Sin persistencia ni reproducción.** No hay `Last-Event-ID`, búfer ni tabla de eventos.
- **Sin polling** como mecanismo principal ni de respaldo.
- **Publicación best-effort y a lo sumo una vez**, con cota de **0,5 s** por intento y sin bucle
  de reintento; Redis Pub/Sub no confirma entrega.
- **Compatible con la 024 y la 025.** La conexión cuenta como una petición del límite de
  120/min por IP y respeta el borde nginx; el fail-open no altera `/ready`.
- **Compatible con el aislamiento de la 010.** La institución sale del contexto de identidad, no
  del cliente ni de la sesión de control.
- **Sin cambios en las reglas de negocio, los contratos existentes ni los códigos de respuesta**
  de las operaciones actuales.
- **Sin PII ni secretos en frames ni logs.** El canal no agrega correo, token, nombre ni datos
  personales. La evidencia de apertura, degradación y recuperación es una **línea de log JSON**
  con `route` plantilla, `resultado`, `motivo` y `request_id`; **no se añade una familia de
  métricas** y `/metrics` no expone SSE (limitación aceptada).
- **La aplicación debe seguir operando sin el canal.** Con el interruptor apagado o el bus caído,
  las vistas cargan y se refrescan como hoy.
- **La ventana de reevaluación de capacidades e institución** es la menor entre la vigencia del
  token y `VIDA_MAXIMA_CONEXION_SEGUNDOS` (300 s por defecto).

## 9. Riesgos y mitigación

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| El proxy de desarrollo o nginx almacena en búfer y los eventos llegan tarde o nunca | Alta | Alto | `proxy_buffering off`, `X-Accel-Buffering: no`, latido menor que el tiempo de lectura y verificación explícita en 4200 y 8080 |
| Las reconexiones agotan el límite de 120/min por IP | Media | Alto | Una conexión por pestaña, renovación atada al token, retroceso con tope y respeto de `Retry-After`; AC-20 y AC-21 lo miden |
| Un evento filtra existencia o actividad de otra institución o de otro Solicitante | Baja | Alto | Audiencia resuelta en servidor, sobre interno separado del frame y sin identificadores serializados; tests con dos instituciones y dos Solicitantes (AC-15/AC-16/AC-27) |
| Un identificador del sobre interno se serializa por error al frame | Baja | Alto | Sobre y frame son tipos distintos; prueba que inspecciona el frame serializado (AC-27) |
| La marca `dashboard` sintética revela el dominio oculto por el `motivo` | Media | Medio | `motivo: "cambio"` fijo en la marca y prueba de frame (AC-28) |
| Redis Pub/Sub pierde un evento y la vista no se entera | Media | Medio | Best-effort declarado; resincronización al abrir/foco y relectura por GET; sin promesa de entrega (D-8, AC-7) |
| La conexión retiene conexiones del pool y bloquea la API | Media | Alto | Copiar el contexto y cerrar las sesiones antes del flujo; prueba con varias conexiones ociosas y pool pequeño (AC-29) |
| Un hub en memoria entrega solo a un worker | Media | Alto | Bus compartido entre procesos (Redis de la 025) y prueba con dos procesos reales (AC-23) |
| La capacidad o la institución cambia y la conexión abierta sigue recibiendo | Media | Medio | Reapertura ≤ 300 s o vigencia del token, reevaluación en cada apertura y AC-31 |
| La publicación bloquea la mutación si el bus se cuelga | Media | Medio | Cota dura de 0,5 s, sin reintento y medición de latencia en AC-8 |
| El refresco interrumpe al usuario que escribe un motivo o cambia filtros | Media | Medio | Refresco silencioso, conservación de estado y prueba con diálogo abierto (AC-14) |
| Las pruebas de flujo son lentas o inestables por tiempos reales | Alta | Medio | Reloj, latido y bus inyectables; intervalos cortos en pruebas; gated de Redis separado |
| La vigencia real del token de Clerk difiere de la supuesta | Media | Medio | Leer la expiración del token validado, no fijar un valor en código y probar con la costura de firma (AC-3) |
| Un cliente sin soporte de streaming queda sin actualización y no lo sabe | Baja | Medio | Estado degradado no bloqueante; la app sigue operable; no se exige sondeo |
| Las aserciones absolutas 74/72 se relajan en lugar de ampliarse | Media | Bajo | Actualización explícita en un solo punto y revisión en AC-24 |
| El número de pestañas supera el límite de conexiones del borde (20 por IP) | Baja | Medio | Una conexión por pestaña; documentar el límite y no abrir canales por vista |
| Un evento se publica antes del commit y anuncia un estado que luego revierte | Baja | Alto | Publicación posterior al commit y prueba de rollback (AC-7) |

## 10. Supuestos y dependencias

- **Depende de:** 004 (tablero), 006 (Clerk), 007 (matriz), 009 (dashboard), 010 (multi-tenant),
  013 (ciclo de vida y detalle), 017 (Superadmin sin lecturas de negocio), 020/021 (recepción y
  desbloqueo) y 024/025 (borde, CORS, Redis y límite de tasa).
- **No depende de:** 015 ni 016; es la antesala técnica de la 016, que sigue pendiente.
- **Supone que** el navegador objetivo soporta respuestas HTTP de larga duración y lectura
  incremental (Chromium/Edge, Firefox y Safari actuales).
- **Supone que** el servidor de desarrollo y nginx pueden configurarse para no almacenar en
  búfer la ruta de eventos.
- **Supone que** Clerk entrega tokens de sesión con vigencia acotada y que `getToken()` devuelve
  uno vigente o `null`; la feature no fija una duración. La expiración se obtiene del token
  validado: la identidad debe exponerla o el endpoint resolverla de los claims.
- **Supone que** el backend puede correr en más de un proceso; el bus compartido lo cubre.
- **Supone que** el cliente Python `redis==8.1.0` y el servidor `redis:7.2-alpine` del Compose son
  compatibles con Pub/Sub y con la reconexión del suscriptor.
- **Supone que** Redis puede estar caído sin impedir el arranque ni la operación de negocio,
  como ya ocurre con el limitador de la 025.
- **Supone que** los datos son QA y la base se reconstruye con `down -v` + `up -d`; no hay
  migración.
- **Supone que** la evidencia de observabilidad es la línea de log JSON del canal; **no se añade
  una familia de métricas** y `/metrics` no expone SSE. Es una limitación aceptada de esta
  entrega.
- **Supone que** la publicación best-effort y la resincronización por GET son suficientes para la
  convergencia; no se promete entrega de eventos.
- **Aprobación requerida:** esta `spec.md` y su `plan.md` antes de tocar `backend/` o
  `frontend/` (`AGENTS.md` §7).

## 11. Plan de verificación de cierre

1. **Línea base:** suites actuales en verde, `/openapi.json` en 74/72 y token `026.1`.
2. **Unitarios:** publicación después del commit y no antes; filtro de audiencia por institución,
   rol, propietario y capacidad; serialización de frames frente al sobre interno; planificador de
   retroceso y agrupador de refrescos.
3. **Integración de contrato:** 401/403/429/503, media type, `listo`, latido con intervalo corto,
   cierre por `exp - 10 s` con la costura de firma/JWKS, ausencia de `id`/`retry` y marca
   `dashboard` sin dominio oculto.
4. **Integración de publicación:** una prueba por mutación del Anexo A —incluidas emisión,
   facturación y cancelación de OC—, una por rechazo/rollback y una por recepción con y sin
   desbloqueo; aislamiento con dos instituciones, dos Solicitantes y fan-out de dos dueños.
5. **Gated de Redis:** dos procesos reales que comparten el bus; caída, recuperación y latencia de
   la mutación con el bus colgado (≤ 0,5 s); límite de tasa con el canal abierto.
6. **Frontend:** hub con flujo falso (frames, reconexión, agrupación, visibilidad y
   resincronización), tablero, detalle y dashboard con eventos simulados, marca `dashboard` y
   conservación de filtros, scroll y diálogos.
7. **4200:** dos o tres sesiones reales, todas las mutaciones, las de compras que tocan el pedido,
   recepción, dashboard, caída y reconexión, pestaña oculta y vuelta a foco.
8. **8080:** reconstruir la imagen, verificar el canal a través de nginx, el latido, la ausencia de
   búfer y la consola limpia.
9. **Documentación y coherencia:** `/openapi.json` 75/73, matriz 73, `stack.md` con la frontera de
   tiempo real, `roadmap.md` con la fila 028, `MEMORY.md`, `deuda-tecnica.md` y la evidencia de la
   feature; grep de rutas y conteos.

## 12. Preguntas abiertas

La aprobación cubre las siguientes decisiones, ya incorporadas en la spec:

1. **Superficie obligatoria:** tablero, detalle y dashboard; la vista de existencias queda fuera y
   el dominio `inventario` se difunde porque alimenta el dashboard y la disponibilidad del pedido
   (D-13, §3.2).
2. **Señal de invalidación:** el frame no transporta datos ni identificadores; el refresco siempre
   es por GET (D-2).
3. **Sobre interno vs. frame:** el bus puede llevar institución y dueños para enrutar; el cliente
   nunca los ve (D-5, AC-27).
4. **Autenticación:** la conexión vive atada al token de Clerk, con cierre en `exp - 10 s` y
   reevaluación al renovar (D-6, AC-3, AC-31).
5. **Dashboard sintético:** la marca `dashboard` se sintetiza por conexión cuando el dominio de
   origen no es visible y nunca nombra el dominio oculto (D-4, D-13, AC-28).
6. **Compras que tocan el pedido:** emisión, facturación, cancelación y recepción; las demás no
   cambian `GET /tickets/{id}` y no se anuncian (D-13, Anexo A, AC-30).
7. **Publicación:** best-effort y a lo sumo una vez, con cota de 0,5 s; la convergencia es por GET
   (D-8, AC-7, AC-8).
8. **Interruptor:** el canal se apaga por configuración y la app sigue operando (D-14, AC-32).

**Dudas reales que la aprobación debe confirmar (no bloquean la redacción):**

1. **Ventana de capacidades e institución.** Se fija en la menor entre la vigencia del token y
   300 s (D-6, AC-31). Si se quiere efecto inmediato al apagar una capacidad, habría que
   reevaluar por evento (una lectura de BD por evento y conexión) o cerrar las conexiones al
   cambiar la capacidad (más superficie y más acoplamiento). La ventana de 5 minutos es la
   propuesta.
2. **Cota de publicación de 0,5 s.** Con el bus colgado, la mutación puede esperar hasta 0,5 s
   antes de responder. Si se prefiere no añadir nada, habría que despachar en segundo plano y
   aceptar que el evento se pierda sin cota; no se recomienda porque complica el ciclo de vida
   de la tarea.
3. **Lista de compras.** La derivación del código es: emisión, facturación, cancelación y
   recepción. El alta/edición en `Borrador`, los proveedores y el preview no cambian
   `GET /tickets/{id}`. Si el usuario quiere anunciar también esas operaciones sin efecto en el
   pedido, es una ampliación de alcance, no un vacío.
4. **Vista de existencias.** Queda fuera de los AC; el dominio `inventario` ya existe, así que
   incluirla después es una suscripción de la vista, no un rediseño. Si debe entrar ahora, se
   agrega un AC de propagación de esa vista.

## 13. Notas de cierre y validación (28/Nov/2026)

> **Veredicto de @reviewer: APROBADO (28/Nov/2026), sin bloqueantes.** Las seis filas «parcial»
> del informe corresponden a verificaciones manuales no ejecutadas o a ambigüedades de redacción
> de esta spec, no a defectos del comportamiento. Estas notas no cambian el comportamiento, la
> numeración ni los AC; el marcado de AC y del roadmap se hace en el cierre, tras la aprobación
> del usuario.

**Evidencia de la validación**

- Backend SQLite: **2323 passed / 135 skipped / 0 failed** (incluye el test nuevo de AC-2).
- Gated PostgreSQL: **4 passed**; gated Redis: **4 passed**; seguridad: **4 passed**.
- Frontend: **758 SUCCESS**; build **`main-UJT3LSFR.js`** (348,36 kB).
- Contrato: `/openapi.json` **75/73**; matriz **73**.
- Recorrido manual del usuario: AC-9, AC-10, AC-11, AC-12, AC-13, AC-14 y humo 8080.
- T13: el contexto de tiempo real resuelve la institución con
  `tenant_service.resolver_contexto_solicitud` en PostgreSQL y con `ambito_service` en SQLite;
  el gated acredita `GET /api/v1/eventos/` **200** con identidad de tenant.
- Cierre (28/Nov/2026): AC-1…AC-32 marcados en §7 con su evidencia, `roadmap.md` en `[x]` y
  `evidencia/README.md` §10 con el veredicto; el test nuevo de AC-2 acredita que la credencial
  solo cuenta en `Authorization`.

**Excepciones aceptadas por el reviewer**

- **T0:** `TestClient` bufferiza SSE; el ajuste quedó documentado como **DT-17**.
- **T14:** el manual de dos workers no se ejecutó; el gated de dos instancias con Redis real y
  `PUBSUB NUMSUB` acredita el fan-out.
- **T21:** el `curl -N` autenticado no se ejecutó; el humo 8080 con sesión real es la evidencia
  equivalente; queda declarado el riesgo residual de 60 s.
- **AC-4:** no se midió el flujo autenticado de 60 s ni la consola en 8080; la configuración y el
  latido lo cubren.
- **Sin capturas nuevas:** la evidencia manual es la confirmación del usuario.

**Observaciones abiertas que se registrarán como deuda al cerrar (no bloquean)**

- **DT-18:** la comprobación de versión del tenant usa `control.version_esquema` en el camino sin
  sesión tenant; no hay fuga, pero no valida literalmente el esquema tenant.
- **DT-19:** `ticket_service._publicar_pedido` lee `institucion_id`/`usuario_id` después del
  commit; conviene capturarlos antes, como hace `inventario_service`.

## Anexo A — Catálogo exhaustivo de mutaciones y avisos

| # | Operación | Dominios anunciados | Audiencia | Condición de publicación |
|---|---|---|---|---|
| 1 | `POST /api/v1/tickets/` | `pedidos` | Administrador y Bodeguero de la institución; Solicitante dueño | Alta confirmada |
| 2 | `PUT /api/v1/tickets/{ticket_id}` | `pedidos` | Ídem | Edición confirmada |
| 3 | `POST /api/v1/tickets/{ticket_id}/aprobacion` | `pedidos` | Ídem | Transición confirmada |
| 4 | `POST /api/v1/tickets/{ticket_id}/retiro` | `pedidos`, `inventario` | Administrador/Bodeguero + dueño; inventario a los tres roles | Retiro confirmado con sus salidas |
| 5 | `POST /api/v1/tickets/{ticket_id}/confirmacion-entrega` | `pedidos` | Administrador/Bodeguero + dueño | Confirmación registrada |
| 6 | `POST /api/v1/tickets/{ticket_id}/anulacion` (desde `EnRevision`) | `pedidos` | Administrador/Bodeguero + dueño | Anulación confirmada |
| 7 | `POST /api/v1/tickets/{ticket_id}/anulacion` (desde `Cerrado`) | `pedidos`, `inventario` | Administrador y Bodeguero; dueño; inventario a los tres roles | Anulación confirmada con devolución |
| 8 | `POST /api/v1/tickets/{ticket_id}/rechazo` | `pedidos` | Administrador/Bodeguero + dueño | Rechazo confirmado |
| 9 | `PATCH /api/v1/tickets/{ticket_id}/estado` | `pedidos` | Administrador/Bodeguero + dueño | Cambio confirmado |
| 10 | `POST /api/v1/inventario/movimientos` | `inventario` | Los tres roles con capacidad `inventario` | Movimiento confirmado |
| 11 | `POST /api/v1/compras/ordenes/{orden_id}/emitir` | `compras`; `pedidos` si el plan asigna a algún pedido | `compras` a Administrador/Bodeguero; `pedidos` a Administrador/Bodeguero y a los dueños de los pedidos asignados | Emisión confirmada con plan con `cantidad_asignada > 0` |
| 12 | `PUT /api/v1/compras/ordenes/{orden_id}/factura` | `compras`; `pedidos` si la OC pasa de `Emitida` a `Facturada` con plan | Ídem | Factura confirmada |
| 13 | `POST /api/v1/compras/ordenes/{orden_id}/cancelar` | `compras`; `pedidos` si cancela una OC `Emitida` con plan | Ídem | Cancelación confirmada |
| 14 | `POST /api/v1/compras/ordenes/{orden_id}/recepcion` | `inventario`, `compras`; `pedidos` si cambia la cadena o desbloquea | Los tres roles para inventario; Administrador/Bodeguero para compras; pedidos a Administrador/Bodeguero y dueños afectados | Recepción confirmada |

Notas del anexo:

1. Las mutaciones 1–9 son las que exige AC-5; la 10, AC-6; las 11–14, AC-30.
2. Una mutación de la tabla puede anunciar más de un dominio; el cliente agrupa y relee una vez
   por vista.
3. **No se anuncian** `POST /compras/ordenes` y `PUT /compras/ordenes/{orden_id}` en `Borrador`,
   `POST`/`GET /compras/proveedores`, `POST /compras/cobertura/preview` ni las lecturas: no
   cambian `GET /tickets/{id}`. Las de administración, catálogo y organización tampoco (D-13 y
   §3.2).
4. Las operaciones que responden 401, 403, 404, 409 o 422, o que revierten, no publican (AC-7).
5. La marca `dashboard` no aparece en esta tabla: es una **sustitución por conexión** de
   `pedidos`/`inventario` cuando el dominio no es visible (AC-28), no un dominio de origen.

## Anexo B — Registro de cambios de esta corrección (28/Nov/2026)

| Hallazgo | Cambio aplicado | Sección |
|---|---|---|
| **B1** | Sobre interno separado del frame; `institucion_id`/`usuario_id` solo para enrutar; fan-out de una recepción con N dueños; prohibición de ids limitada al frame; AC-27 | D-5, §5.3, §6.1, AC-18, AC-27 |
| **B2** | Publicación best-effort y a lo sumo una vez; se elimina «al menos una vez»; convergencia por GET; AC-7/AC-8 condicionadas al bus sano | D-8, §5.2, §5.6, AC-7, AC-8 |
| **M3** | Fila 7 del Anexo A incluye al Bodeguero en `pedidos` | Anexo A |
| **M4** | AC-9, AC-11 y AC-12 acotan «otro usuario» a Administrador/Bodeguero (o remiten a AC-16) | AC-9, AC-11, AC-12 |
| **M5** | Marca sintética `dashboard` por conexión, solo con capacidad `dashboard`, sin dominio ni motivo oculto; AC-28; actualización de D-4, D-13, §5.3, §5.4, §6.1, §6.3 y AC-17 | D-4, D-13, §5.3, §5.4, §6.1, §6.3, AC-12, AC-17, AC-28 |
| **M6** | Identidad, institución, rol, capacidades y expiración copiadas antes del flujo; sesiones cerradas antes de la espera; AC-29 | §5.1, §8, AC-29 |
| **M7** | La expiración sale del token validado; cierre en `exp - 10 s`; vida máxima 300 s; AC-3 con la costura de firma/JWKS | D-6, §5.1, AC-3, AC-31 |
| **M8** | Emisión, facturación, cancelación y recepción de OC anuncian `compras` y `pedidos` cuando cambian `GET /tickets/{id}`; alta/edición en Borrador, proveedores y preview no anuncian; AC-30 | D-13, §3.2, §5.2, Anexo A, AC-30 |
| **M9** | Reevaluación de institución y capacidades en cada reapertura; ventana máxima 300 s o vigencia del token; AC-31 | D-6, §5.1, §5.5, §5.6, AC-31 |
| **m10** | `redis==8.1.0` es el cliente Python; `redis:7.2-alpine` es el servidor | D-12, §8, §10 |
| **m11** | AC-32 para el interruptor: 503, sin conexión y app operativa | AC-32 |
| **m12** | «Navegación» como causa de cierre sustituida por salida de la aplicación/cierre de pestaña | §5.1 |
| **m13** | AC-15/AC-16 hablan de «ningún frame `cambio` de esa mutación», no de ningún frame | AC-15, AC-16 |
| **m14** | AC-23 exige dos procesos reales o hubs aislados; el manual de dos workers es la evidencia principal | AC-23 |
| **m15** | Cota dura de 0,5 s en la publicación y medición de latencia con el bus colgado | D-8, §5.2, §8, AC-8 |
| **m16** | Evidencia de observabilidad: línea de log JSON por apertura/cierre/degradación/recuperación; sin familia de métricas nueva y limitación declarada | §8, §10, AC-8 |
| **m17** | Roadmap: frase «Siguiente feature» y fila 028 con `[ ]`; bullet del Sprint 7 | `roadmap.md` |
| **m18** | D-2 lista `GET /compras/ordenes` como relectura opcional del panel, fuera de la superficie mínima; sin AC implícita | D-2, §5.4 |
| **m19** | AC-14 mide placeholder, scroll, filtros, orden, búsqueda, pestaña y diálogo; AC-21 fija 2–3 sesiones, 3 minutos, ≤3 aperturas, `X-RateLimit-Remaining > 0` y 0×429 | AC-14, AC-21 |
| **m20** | §12 sustituye «Ninguna» por las decisiones que cubre la aprobación y cuatro dudas reales | §12 |
