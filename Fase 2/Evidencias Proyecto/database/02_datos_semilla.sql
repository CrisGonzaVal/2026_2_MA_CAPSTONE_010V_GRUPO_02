-- =====================================================
-- COMPUSTOCK ERP - DATOS SEMILLA + TENANTS (instalacion limpia)
-- Base de datos: apt_erp
-- PostgreSQL 16
-- =====================================================
--
-- PROPOSITO
--   Llenar la instalacion creada por `01_esquema.sql`:
--     1. sembrar en `control` los datos de QA (capacidades, sedes,
--        departamentos, usuarios, catalogo, stock, movimientos, tickets);
--     2. repartir esos datos a los esquemas `tenant_*` (una institucion por
--        esquema), dejando `control` como contexto global;
--     3. poblar `control.mapa_usuario_esquema` y `control.version_esquema`.
--   `control.registro_motivo_constancia` (Feature 017) queda VACIA: es evidencia
--   recuperable generada por las operaciones administrativas, no semilla.
--   Los dos historiales del catalogo (Feature 014) tambien quedan VACIOS en
--   control y en cada tenant: registrar una transicion ficticia inventaria
--   trazabilidad. La semilla solo siembra producto/categoria en estado activo.
--   La Feature 020 siembra TRES PROVEEDORES en el catalogo global
--   `control.proveedor` y los replica en cada tenant con el mismo id; las
--   ordenes, detalles y facturas de compra quedan VACIAS en control y en los
--   tenants (son datos operativos, no semilla).
--
-- ORDEN DE EJECUCION (no lo cambies sin leer esto)
--   PostgreSQL ejecuta los .sql de esta carpeta solo al crear el volumen, en
--   orden alfabetico y con ON_ERROR_STOP=1. `02_` va DESPUES de `01_`, que crea
--   `control` y los esquemas tenant; si se invierte, la semilla aborta.
--
-- ATOMICIDAD Y GUARDIA FAIL-CLOSED
--   Todo el archivo corre en una sola transaccion (BEGIN/COMMIT). La guardia de
--   la seccion 0 aborta ANTES de tocar nada si la base ya tiene filas de
--   negocio; ese es el motivo por el que el reset del entorno de QA se hace
--   recreando el volumen, no reejecutando la semilla:
--     docker compose -f docker-compose.yml down -v
--     docker compose -f docker-compose.yml up -d db
--   No se usa TRUNCATE: la guardia garantiza que la base esta limpia y
--   `control.institucion` (la topologia sembrada por `01_`) no se toca.
--
-- ESQUEMA (Feature 010)
--   Las tablas canonicas se referencian sin prefijo: el `search_path` de la base
--   apunta a `control, public`. Los tenants se referencian siempre calificados.
--
-- DATOS
--   Cuatro instituciones (INST-001..INST-004). INST-001 e INST-002 quedan
--   completas (departamentos, usuarios, catalogo, stock, movimientos y
--   tickets); INST-003 e INST-004 conservan sus departamentos y usuarios. Los
--   homonimos entre instituciones ("Papeleria", "Resma Carta 75g A4", ...) son
--   DELIBERADOS: filas independientes con ids y stock distintos.
--   El reparto de sedes es el de la Feature 011: INST-001 -> 2, INST-002 -> 3,
--   INST-003 -> 4, INST-004 -> 2; cada departamento va a UNA sede por
--   round-robin sobre ids ascendentes. `stock_sede` es el unico saldo vigente
--   desde la Feature 026: la antigua tabla `inventario` ya no existe.
--
-- CONVENCION DE IDs
--   Los INSERT declaran el id de forma explicita (`OVERRIDING SYSTEM VALUE`)
--   para que el QA manual pueda referenciar filas concretas. Eso obliga a
--   sincronizar las secuencias de control (seccion 13) y de cada tenant (lo
--   hace `resetear_identidades` en el bloque de reparto).
--
-- RESTRICCION - estado_ticket
--   El servicio de tickets reconoce los estados terminales por NOMBRE
--   (`Cerrado`, `Anulado`), nunca por un id fijo. `Anulado` queda FUERA de la
--   secuencia lineal y solo se alcanza por anulacion o rechazo con motivo.
--
-- VERSION OBJETIVO DEL DDL
--   026.0 (`VERSION_ESQUEMA_OBJETIVO` en backend/app/core/config.py).
-- =====================================================

BEGIN;

SET search_path TO control, public;

-- Nombre determinista del esquema tenant: espejo EXACTO en SQL de
-- `app.services.tenant_service.nombre_esquema_para_institucion`.
-- Identica a la de 01_esquema.sql; se repite aqui porque pg_temp no se comparte
-- entre archivos.
CREATE OR REPLACE FUNCTION pg_temp.nombre_esquema_tenant(p_institucion_id text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $nombre$
    SELECT 'tenant_'
        || left(
             btrim(
               regexp_replace(
                 lower(
                   regexp_replace(
                     normalize(btrim(p_institucion_id), NFKD),
                     '[^[:ascii:]]', '', 'g'
                   )
                 ),
                 '[^a-z0-9]', '_', 'g'
               ),
               '_'
             ),
             47
           )
        || '_'
        || substr(encode(sha256(convert_to(btrim(p_institucion_id), 'UTF8')), 'hex'), 1, 8);
$nombre$;

-- =====================================================
-- 0. GUARDIA FAIL-CLOSED
-- =====================================================
-- Aborta antes de tocar nada si `control` o cualquier tenant ya tienen filas de
-- negocio. `control.institucion` se excluye: esas cuatro filas son la topologia
-- que siembra `01_esquema.sql`. Si alguna tabla esperada no existe, tambien
-- aborta (cierra por defecto).
DO $guardia$
DECLARE
    v_institucion_id text;
    v_esquema text;
    v_tabla text;
    v_conteo bigint;
    v_total bigint := 0;
    v_instituciones integer;
BEGIN
    SELECT count(*) INTO v_instituciones FROM control.institucion;
    IF v_instituciones <> 4 THEN
        RAISE EXCEPTION
            'Semilla QA abortada: control.institucion tiene % fila(s); se esperan 4 (01_ no corrio o la topologia cambio).',
            v_instituciones;
    END IF;

    FOREACH v_tabla IN ARRAY ARRAY[
        'funcion_institucion', 'sede', 'departamento', 'rol', 'usuario',
        'departamento_encargado', 'categoria', 'producto',
        'stock_sede', 'movimiento_inventario', 'prioridad', 'estado_ticket',
        'ticket', 'detalle_ticket', 'historial_transicion_ticket',
        'historial_transicion_producto', 'historial_transicion_categoria',
        'proveedor', 'orden_compra', 'detalle_orden_compra', 'factura_compra',
        'orden_compra_ticket',
        'mapa_usuario_esquema', 'version_esquema', 'registro_motivo_constancia'
    ] LOOP
        EXECUTE format('SELECT count(*) FROM control.%I', v_tabla) INTO v_conteo;
        v_total := v_total + v_conteo;
    END LOOP;

    FOR v_institucion_id IN SELECT institucion_id FROM control.institucion ORDER BY institucion_id LOOP
        v_esquema := pg_temp.nombre_esquema_tenant(v_institucion_id);
        IF to_regnamespace(v_esquema) IS NULL THEN
            RAISE EXCEPTION 'Semilla QA abortada: falta el esquema tenant % (01_ no lo creo).', v_esquema;
        END IF;

        FOREACH v_tabla IN ARRAY ARRAY[
            'institucion', 'sede', 'departamento', 'rol', 'usuario',
            'departamento_encargado', 'categoria', 'producto',
            'stock_sede', 'movimiento_inventario', 'prioridad', 'estado_ticket',
            'ticket', 'detalle_ticket', 'historial_transicion_ticket',
            'historial_transicion_producto', 'historial_transicion_categoria',
            'proveedor', 'orden_compra', 'detalle_orden_compra', 'factura_compra',
            'orden_compra_ticket',
            'version_esquema'
        ] LOOP
            IF to_regclass(format('%I.%I', v_esquema, v_tabla)) IS NULL THEN
                RAISE EXCEPTION 'Semilla QA abortada: falta la tabla %.% en el tenant.', v_esquema, v_tabla;
            END IF;
            EXECUTE format('SELECT count(*) FROM %I.%I', v_esquema, v_tabla) INTO v_conteo;
            v_total := v_total + v_conteo;
        END LOOP;
    END LOOP;

    IF v_total > 0 THEN
        RAISE EXCEPTION
            'Semilla QA abortada: la base ya contiene % fila(s) de negocio; no se ejecuta ningun cambio. Reset QA = recrear el volumen (docker compose down -v).',
            v_total;
    END IF;

    RAISE NOTICE 'Semilla QA: base limpia (4 instituciones, tenants vacios), se permite continuar.';
END;
$guardia$;

-- =====================================================
-- 1a. FUNCION_INSTITUCION  (28 filas = 4 x 7)  [Feature 012, auxiliar]
-- =====================================================
-- Cada institucion nace con sus siete capacidades funcionales habilitadas
-- (conjunto cerrado ampliado por la Feature 020 con `compras`). `activo` de
-- `institucion` toma su DEFAULT TRUE (la semilla no nombra la columna).
-- `funcion_institucion` es SOLO de control: el constructor no la copia a ningun
-- tenant.

INSERT INTO funcion_institucion (institucion_id, funcion, habilitada)
SELECT i.institucion_id, f.funcion, TRUE
FROM institucion i
CROSS JOIN (
    VALUES ('catalogo'), ('inventario'), ('tickets'),
           ('kanban'), ('dashboard'), ('gestion_organizacional'),
           ('compras')
) AS f(funcion);

-- =====================================================
-- 1a-bis. PROVEEDOR  (3 filas)  [Feature 020, catalogo global]
-- =====================================================
-- Catalogo global compartido: `control.proveedor` es la fuente de verdad y cada
-- tenant recibe una replica con el MISMO `proveedor_id` (sin identidad propia).
-- Las filas nacen activas; la Feature 020 no expone baja/reactivacion.

INSERT INTO proveedor (proveedor_id, rut, razon_social, nombre_fantasia, giro, correo, telefono) OVERRIDING SYSTEM VALUE VALUES
(1, '76.543.210-8', 'Papelera del Pacifico SpA',            'Papelera Pacifico',  'Venta de articulos de oficina',            'ventas@papelerapacifico.cl',     '+56 2 2345 6789'),
(2, '77.654.321-K', 'Suministros Corporativos Andinos Ltda.', 'Suministros Andinos', 'Distribucion de insumos de oficina',       'contacto@suministrosandinos.cl', '+56 2 2987 6543'),
(3, '78.765.432-1', 'Tecnologia y Toner Express S.A.',       'Toner Express',      'Comercializacion de insumos de impresion', 'pedidos@tonerexpress.cl',        '+56 2 2555 1212');

-- =====================================================
-- 1b. SEDE  (11 filas)  [Feature 011]
-- =====================================================
-- Reparto fijo de D-7 por institucion: INST-001 -> 2, INST-002 -> 3,
-- INST-003 -> 4, INST-004 -> 2. Los ids son explicitos para que la regla
-- round-robin (departamentos por id ascendente, sedes por id ascendente,
-- indice i mod N) sea reproducible y referenciable en el QA manual.

INSERT INTO sede (sede_id, nombre, direccion, institucion_id) OVERRIDING SYSTEM VALUE VALUES
(1,  'Sede Providencia',        'Av. Providencia 1234, Santiago',    'INST-001'),
(2,  'Sede Maipu',              'Av. Pajaritos 2200, Maipu',         'INST-001'),
(3,  'Sede Los Robles',         'Calle Los Robles 45, Maipu',        'INST-002'),
(4,  'Sede CFS Norte Poniente', 'Av. Colon 3300, Maipu',             'INST-002'),
(5,  'Sede CFS Norte Oriente',  'Pasaje El Bosque 12, Renca',        'INST-002'),
(6,  'Sede La Ladera',          'Camino La Ladera 890, Lo Barnechea','INST-003'),
(7,  'Sede Cordillera Centro',  'Av. Apoquindo 4500, Las Condes',    'INST-003'),
(8,  'Sede Cordillera Sur',     'Av. Vicuna Mackenna 8900, La Florida','INST-003'),
(9,  'Sede Cordillera Norte',   'Av. Recoleta 1200, Recoleta',       'INST-003'),
(10, 'Sede Municipal',          'Plaza de Armas s/n, Talagante',     'INST-004'),
(11, 'Sede Oficina Barrio Sur', 'Av. Bernardo OHiggins 1450, Talagante','INST-004');

-- =====================================================
-- 2. DEPARTAMENTO  (10 filas)
-- =====================================================
-- INST-001 aporta 7 departamentos (1..7); INST-002 el 8; INST-003 el 9;
-- INST-004 el 10. Los usuarios y el ambito se derivan de aqui.
-- Feature 011 (D-7): cada departamento queda en UNA sede por la regla
-- round-robin (indice del departamento en su institucion, por id ascendente,
-- modulo el numero de sedes de esa institucion):
--   INST-001 (2 sedes 1,2): deps 1..7 -> 1,2,1,2,1,2,1
--   INST-002 (3 sedes 3,4,5): dep 8   -> 3
--   INST-003 (4 sedes 6..9):  dep 9   -> 6
--   INST-004 (2 sedes 10,11): dep 10  -> 10

INSERT INTO departamento (departamento_id, nombre_dep, descripcion, institucion_id, sede_id) OVERRIDING SYSTEM VALUE VALUES
(1,  'Direccion',              'Direccion_general y planificacion',       'INST-001', 1),
(2,  'Secretaria',             'Recepcion, correspondencia y agenda',     'INST-001', 2),
(3,  'Administracion',         'Pagos, compras y contabilidad',            'INST-001', 1),
(4,  'RRHH',                   'Seleccion y remuneraciones y contratos',    'INST-001', 2),
(5,  'Docencia',               'Coordinacion de salas/material didactico',  'INST-001', 1),
(6,  'Biblioteca',             'Catalogacion y prestamo de material',      'INST-001', 2),
(7,  'Servicios Generales',    'Mantenimiento, aseo y seguridad',          'INST-001', 1),
(8,  'AtencionPrimaria',       'Recepcion de pacientes y fichas',         'INST-002', 3),
(9,  'CoordinacionAcademica',  'Programacion de cursos y matriculas',      'INST-003', 6),
(10, 'OficinaGeneral',         'Oficina de Partes Municipal',                'INST-004', 10);

-- =====================================================
-- 3. ROL  (4 filas)  [GLOBAL, sin institucion - D-5/AC-3]
-- =====================================================
-- Los tres actores del sistema mas superadmin, segun AGENTS.md seccion 2.

INSERT INTO rol (rol_id, nombre_rol, descripcion) OVERRIDING SYSTEM VALUE VALUES
(1, 'Superadmin',        'Administrador global de la plataforma SaaS'),
(2, 'Administrador',     'Gestiona usuarios, departamentos y catalogo maestro'),
(3, 'Bodeguero',         'Gestiona stock fisico y despacha pedidos aprobados'),
(4, 'Solicitante',       'Funcionario que consulta stock y emite tickets');

-- =====================================================
-- 4. USUARIO  (13 filas)
-- =====================================================
-- Clerk es la unica autoridad de autenticacion (Feature 006): el usuario local
-- no guarda credencial alguna. El vinculo con Clerk se resuelve por `correo`
-- (UNIQUE) contra el correo primario verificado, no por contrasena.
-- La institucion del usuario NO se guarda aqui: se deriva de su departamento.
-- Feature 011 (D-5): `sede_id` solo se puebla para los Bodegueros (rol 3) y con
-- la sede de su propio departamento; el resto queda NULL porque no opera stock:
--   usuario 6 (dep 6 -> sede 2), usuario 7 (dep 7 -> sede 1) y usuario 12
--   (dep 6 -> sede 2).
-- Los usuarios 11 y 12 (Feature 013) son las cuentas QA de ciclo de vida: sus
-- correos `+clerk_test@example.com` existen en la instancia dev de Clerk con
-- codigo de verificacion fijo 424242, de modo que cualquier clon puede probar
-- el circuito Solicitante -> Bodeguero sin crear usuarios a mano. Ambos estan
-- en el departamento 6 (Biblioteca, Sede 2) para que el ticket emitido por el
-- Solicitante se despache desde la misma sede que opera el Bodeguero.
-- El usuario 13 es la cuenta QA del Administrador institucional en INST-001.

INSERT INTO usuario (usuario_id, nombre, apellido, correo, departamento_id, rol_id, sede_id) OVERRIDING SYSTEM VALUE VALUES
(1,  'Camila',   'Fernandez', 'camila.fernandez@losalpes.cl',   1, 2, NULL),
(2,  'Diego',    'Munoz',     'diego.munoz@losalpes.cl',       2, 4, NULL),
(3,  'Valentina', 'Reyes',     'valentina.reyes@losalpes.cl',   3, 2, NULL),
(4,  'Sebastian','Gutierrez', 'sebastian.gutierrez@losalpes.cl', 4, 2, NULL),
(5,  'Isabel',   'Contreras', 'isabel.contreras@losalpes.cl',  5, 4, NULL),
(6,  'Andres',   'Vargas',    'andres.vargas@losalpes.cl',     6, 3, 2),
(7,  'Marcela',  'Nunez',     'marcela.nunez@losalpes.cl',     7, 3, 1),
(8,  'Felipe',   'Soto',      'felipe.soto@cfsnorte.cl',       8, 4, NULL),
(9,  'Carla',    'Mancilla',  'carla.mancilla@cordillera.cl',  9, 4, NULL),
(10, 'Andres',   'Pino',      'andres.pino@talagante.cl',      10, 2, NULL),
(11, 'Paula',    'Rojas',     'solicitante.test+clerk_test@example.com', 6, 4, 2),
(12, 'Roberto',  'Diaz',      'bodeguero.test+clerk_test@example.com',   6, 3, 2),
(13, 'Admin',    'QA',        'admin020.test+clerk_test@example.com',     1, 2, NULL);

-- =====================================================
-- 4b. DEPARTAMENTO_ENCARGADO  (5 filas)  [Feature 011, auxiliar]
-- =====================================================
-- Encargado de departamento = usuario Solicitante (rol 4) del MISMO departamento
-- (spec D-4); no concede permisos adicionales. En la semilla hay un Solicitante
-- por departamento, de modo que se asocia 1:1 al departamento al que pertenece.
-- La tabla admite varios encargados por departamento; la compatibilidad la
-- valida el servicio, no un trigger.
--   departamento 2 -> usuario 2 | departamento 5 -> usuario 5
--   departamento 6 -> usuario 11 (QA 013) | departamento 8 -> usuario 8
--   departamento 9 -> usuario 9

INSERT INTO departamento_encargado (departamento_encargado_id, departamento_id, usuario_id) OVERRIDING SYSTEM VALUE VALUES
(1, 2, 2),
(2, 5, 5),
(3, 6, 11),
(4, 8, 8),
(5, 9, 9);

-- =====================================================
-- 5. CATEGORIA  (10 filas)
-- =====================================================
-- Catalogo de insumos de ofimatica, AHORA por institucion (D-1).
--   INST-001 -> categorias 1..6
--   INST-002 -> categorias 7..10
-- HOMONIMOS DELIBERADOS: 'Papeleria' existe con id 1 (INST-001) y con id 7
-- (INST-002); 'Toner y Cartuchos' con id 2 (INST-001) y 8 (INST-002);
-- 'Organizacion' con id 4 (INST-001) y 10 (INST-002). Son filas independientes.
-- Feature 014 (D-3/AC-13): todo el catalogo sembrado nace ACTIVO. Se declara
-- explicitamente aunque el DDL tenga DEFAULT TRUE, para que la semilla no
-- dependa de ese default y la verificacion gated lea el estado real.

INSERT INTO categoria (categoria_id, nombre_cat, descripcion_cat, institucion_id, activo) OVERRIDING SYSTEM VALUE VALUES
(1,  'Papeleria',           'Hojas, resmas y sobres',                'INST-001', TRUE),
(2,  'Toner y Cartuchos',   'Consumibles de impresion',              'INST-001', TRUE),
(3,  'Escritura',           'Lapices, marcadores y rotuladores',     'INST-001', TRUE),
(4,  'Organizacion',        'Folders, archivadores y separadores',   'INST-001', TRUE),
(5,  'Oficina',             'Clip, fasteners y consumibles',         'INST-001', TRUE),
(6,  'Limpieza',            'Productos de aseo y sanitizacion',      'INST-001', TRUE),
(7,  'Papeleria',           'Hojas, resmas y sobres',                'INST-002', TRUE),
(8,  'Toner y Cartuchos',   'Consumibles de impresion',              'INST-002', TRUE),
(9,  'Insumos Clinicos',    'Guantes, gasas y material de atencion', 'INST-002', TRUE),
(10, 'Organizacion',        'Folders, archivadores y separadores',   'INST-002', TRUE);

-- =====================================================
-- 6. PRODUCTO  (14 filas)
-- =====================================================
-- Cada producto pertenece a la institucion de su categoria (FK compuesta
-- producto(institucion_id, categoria_id) -> categoria(institucion_id, categoria_id)).
--   INST-001 -> productos 1..10 (categorias 1..6)
--   INST-002 -> productos 11..14 (categorias 7..10)
-- HOMONIMOS DELIBERADOS entre instituciones (mismo `nombre`):
--   'Resma Carta 75g A4'  -> prod 1 (INST-001) y prod 11 (INST-002)
--   'Toner HP 26A Negro'  -> prod 2 (INST-001) y prod 12 (INST-002)
--   'Folder Manila Carta' -> prod 3 (INST-001) y prod 14 (INST-002)
-- Para INST-001 tres productos quedan por DEBAJO de su stock_minimo a proposito,
-- para que el dashboard muestre alertas reales en el QA manual:
--   producto 7 (Toner Negro 26A Comp.) -> 3 < 10
--   producto 8 (Grapadora Estandar)    -> 1 < 5
--   producto 9 (Rotulador Marcador)    -> 6 < 12
-- Feature 014 (D-3/AC-13): todos nacen ACTIVOS, explicitamente.

INSERT INTO producto (producto_id, nombre, descripcion, unidad_medida, stock_minimo, categoria_id, institucion_id, activo) OVERRIDING SYSTEM VALUE VALUES
(1,  'Resma Carta 75g A4',      'Resma de 500 hojas tamano carta',          'RESMA',  20, 1,  'INST-001', TRUE),
(2,  'Toner HP 26A Negro',      'Cartucho de toner negro original HP26A',   'UNIDAD', 10, 2,  'INST-001', TRUE),
(3,  'Folder Manila Carta',     'Carpeta de cartulina tamano carta',        'UNIDAD', 25, 4,  'INST-001', TRUE),
(4,  'Boligrafo Bic Cristal',   'Boligrafo punta fina color negro',         'UNIDAD', 30, 3,  'INST-001', TRUE),
(5,  'Clip Metrico 33mm',       'Clip de metal de 33mm en caja x100',       'CAJA',   15, 5,  'INST-001', TRUE),
(6,  'Cinta Adhesiva 48mm',     'Cinta transparente de 48mm x 100m',        'ROLLO',  12, 6,  'INST-001', TRUE),
(7,  'Toner Negro 26A Comp.',   'Cartucho compatible negro para HP26A',     'UNIDAD', 10, 2,  'INST-001', TRUE),
(8,  'Grapadora Estandar',      'Grapadora de escritorio con grapa 24/6',   'UNIDAD',  5, 5,  'INST-001', TRUE),
(9,  'Rotulador Marcador',      'Rotulador permanente punta gruesa',        'UNIDAD', 12, 3,  'INST-001', TRUE),
(10, 'Papel Premium A4',        'Papel de presentacion alto gramaje',       'RESMA',  10, 1,  'INST-001', TRUE),
(11, 'Resma Carta 75g A4',      'Resma de 500 hojas tamano carta',          'RESMA',  20, 7,  'INST-002', TRUE),
(12, 'Toner HP 26A Negro',      'Cartucho de toner negro original HP26A',   'UNIDAD', 10, 8,  'INST-002', TRUE),
(13, 'Guantes de Latex M',      'Caja de guantes de latex talla M',         'CAJA',   40, 9,  'INST-002', TRUE),
(14, 'Folder Manila Carta',     'Carpeta de cartulina tamano carta',        'UNIDAD', 25, 10, 'INST-002', TRUE);

-- =====================================================
-- 7. STOCK_SEDE  (14 filas)  [Feature 011; unico saldo desde la 026]
-- =====================================================
-- Saldo vigente por (sede, producto): UNIQUE (sede_id, producto_id) y
-- CHECK (stock_actual >= 0). `institucion_id` es la de la sede y el producto, que
-- las FK compuestas obligan a que coincida.
-- Saldos por sede (la antigua tabla `inventario` ya no existe):
--   sede 1 (deps 1,3,5,7): prods 1 (50), 2 (18), 6 (48), 7 (3), 8 (1)
--   sede 2 (deps 2,4,6):   prods 3 (200), 4 (150), 5 (45), 9 (12), 10 (45)
--   sede 3 (dep 8):        prods 11 (12), 12 (9), 13 (8), 14 (60)
-- Los saldos 8 y 9 (45 y 12) incorporan los movimientos 1..3 de la seccion 8;
-- su base antes de esos movimientos era 35 y 6, respectivamente.

INSERT INTO stock_sede (stock_sede_id, stock_actual, sede_id, producto_id, institucion_id) OVERRIDING SYSTEM VALUE VALUES
(1,  50,  1, 1,  'INST-001'),
(2,  18,  1, 2,  'INST-001'),
(3,  48,  1, 6,  'INST-001'),
(4,  3,   1, 7,  'INST-001'),
(5,  1,   1, 8,  'INST-001'),
(6,  200, 2, 3,  'INST-001'),
(7,  150, 2, 4,  'INST-001'),
(8,  45,  2, 5,  'INST-001'),
(9,  12,  2, 9,  'INST-001'),
(10, 45,  2, 10, 'INST-001'),
(11, 12,  3, 11, 'INST-002'),
(12, 9,   3, 12, 'INST-002'),
(13, 8,   3, 13, 'INST-002'),
(14, 60,  3, 14, 'INST-002');

-- =====================================================
-- 8. MOVIMIENTO_INVENTARIO  (3 filas)
-- =====================================================
-- CHECK (cantidad > 0) y CHECK (tipo_movimiento IN ('ENTRADA','SALIDA')).
-- `stock_sede_id` es obligatorio desde la 026 y solo los saldos 8 y 9 tienen
-- historial. Cuadre: saldo 8 = 35 + 10 = 45; saldo 9 = 6 + 21 - 15 = 12.
-- INST-002 conserva 4 saldos sin movimientos: es el resultado esperado de
-- descartar los 14 movimientos legados.

INSERT INTO movimiento_inventario (
    movimiento_id, tipo_movimiento, cantidad, fecha_movimiento, observacion, stock_sede_id
) OVERRIDING SYSTEM VALUE VALUES
(1, 'ENTRADA', 10, CURRENT_TIMESTAMP - INTERVAL '12 days', 'Compra de resmas para bodega', 8),
(2, 'ENTRADA', 21, CURRENT_TIMESTAMP - INTERVAL '9 days',  'Compra de toner para bodega',  9),
(3, 'SALIDA',  15, CURRENT_TIMESTAMP - INTERVAL '7 days',  'Entrega parcial de toner',     9);

-- =====================================================
-- 9. PRIORIDAD  (3 filas)  [GLOBAL, sin institucion - D-5/AC-3]
-- =====================================================

INSERT INTO prioridad (prioridad_id, nombre, descripcion) OVERRIDING SYSTEM VALUE VALUES
(1, 'Alta',  'Necesario para operar en el corto plazo'),
(2, 'Media', 'Requiere reposicion pero no bloquea la operacion'),
(3, 'Baja',  'Puede esperar a la siguiente compra periodica');

-- =====================================================
-- 10. ESTADO_TICKET  (5 filas)  [GLOBAL, sin institucion - D-5/AC-3]
-- =====================================================
-- El orden de las primeras cuatro filas es el orden del flujo lineal: el
-- servicio lo lee por estado_id ascendente. El id de "Cerrado" ya no es
-- critico: el cierre se reconoce por nombre (Feature 004). "Anulado" (Feature
-- 013) es la quinta y ultima fila del catalogo pero queda FUERA de la
-- secuencia lineal: es terminal por NOMBRE junto a "Cerrado", alcanzable solo
-- por anulacion o rechazo con motivo (D-1/D-6 de la 013) y nunca como estado
-- inicial de alta (D-11) ni por el cambio de estado de la 004.

INSERT INTO estado_ticket (estado_id, nombre, descripcion) OVERRIDING SYSTEM VALUE VALUES
(1, 'Pendiente',   'Ticket creado, aun sin revision'),
(2, 'EnRevision',  'Revisando justificacion y disponibilidad'),
(3, 'EnCurso',     'Aprobado y en preparacion de despacho'),
(4, 'Cerrado',     'Despachado y con fecha de cierre registrada'),
(5, 'Anulado',     'Cancelado antes del despacho; anulado o rechazado con motivo en el historial');

-- =====================================================
-- 11. TICKET  (10 filas)
-- =====================================================
-- `institucion_id` se deriva del solicitante (usuario -> departamento ->
-- institucion). Ningun ticket usa un solicitante de otra institucion que la de
-- sus productos. Reparto en los 4 estados; los Cerrados traen fecha_cierre.
--   INST-001 -> tickets 1..8 (solicitantes 1..7, departamentos 1..7)
--   INST-002 -> tickets 9..10 (solicitante 8, departamento 8)
-- Feature 011 (D-5/AC-9): `sede_id` es la instantanea de la sede vigente del
-- departamento del solicitante al crearse el ticket (2 -> sede 1, 3 -> 1,
-- 4 -> 2, 5 -> 1, 6 -> 2, 1 -> 1, 8 -> 3). Un cambio posterior de sede del
-- departamento NO reescribe estos tickets.

INSERT INTO ticket (ticket_id, usuario_id, prioridad_id, estado_id, asunto, descripcion, fecha_creacion, fecha_cierre, institucion_id, sede_id) OVERRIDING SYSTEM VALUE VALUES
(1,  2,  2,  1, 'Resmas para sala de computacion',   'Solicitud de 10 resmas para el curso de referencia.',   CURRENT_TIMESTAMP - INTERVAL '2 days',  NULL, 'INST-001', 2),
(2,  5,  1,  1, 'Toner urgente para impresora',       'La impresora de la sala 3 quedo sin toner.',            CURRENT_TIMESTAMP - INTERVAL '2 days',  NULL, 'INST-001', 1),
(3,  3,  3,  2, 'Folders para archivo de pagos',       'Carpetas para ordenar comprobantes del mes.',          CURRENT_TIMESTAMP - INTERVAL '3 days',  NULL, 'INST-001', 1),
(4,  2,  2,  2, 'Boligrafos para secretaria',          'Reposicion del stock de escritura.',                    CURRENT_TIMESTAMP - INTERVAL '4 days',  NULL, 'INST-001', 2),
(5,  3,  1,  3, 'Grapadoras para oficina',             'Grapadoras de reemplazo para el area de pagos.',        CURRENT_TIMESTAMP - INTERVAL '5 days',  NULL, 'INST-001', 1),
(6,  1,  2,  3, 'Clip metalico para archivo',          'El clip se perdio en la mudanza.',                      CURRENT_TIMESTAMP - INTERVAL '6 days',  NULL, 'INST-001', 1),
(7,  4,  3,  4, 'Cintas para sellar sobres',           'Reposicion de cintas de la oficina.',                   CURRENT_TIMESTAMP - INTERVAL '9 days',  CURRENT_TIMESTAMP - INTERVAL '7 days', 'INST-001', 2),
(8,  6,  2,  4, 'Rotuladores para inventario',         'Rotuladores para etiquetar activos.',                   CURRENT_TIMESTAMP - INTERVAL '12 days', CURRENT_TIMESTAMP - INTERVAL '10 days', 'INST-001', 2),
(9,  8,  1,  2, 'Guantes para box de atencion',        'Insumos clinicos para la atencion primaria.',           CURRENT_TIMESTAMP - INTERVAL '3 days',  NULL, 'INST-002', 3),
(10, 8,  2,  4, 'Resmas para fichas de pacientes',     'Resmas para imprimir fichas en la recepcion.',          CURRENT_TIMESTAMP - INTERVAL '8 days',  CURRENT_TIMESTAMP - INTERVAL '6 days', 'INST-002', 3);

-- =====================================================
-- 12. DETALLE_TICKET  (10 filas)
-- =====================================================
-- CHECK (cantidad_solicitada > 0) y (cantidad_entregada >= 0) respetados.
-- `institucion_id` se deriva del ticket y el producto debe ser de esa misma
-- institucion (FK compuesta). Los tickets Cerrados (estado 4) llevan
-- cantidad_entregada = solicitada, coherente con su despacho.

INSERT INTO detalle_ticket (detalle_ticket_id, ticket_id, producto_id, cantidad_solicitada, cantidad_entregada, institucion_id) OVERRIDING SYSTEM VALUE VALUES
(1,  1,  1,  10,  0,  'INST-001'),
(2,  2,  2,  2,   0,  'INST-001'),
(3,  3,  3,  50,  0,  'INST-001'),
(4,  4,  4,  24,  0,  'INST-001'),
(5,  5,  8,  3,   0,  'INST-001'),
(6,  6,  5,  4,   0,  'INST-001'),
(7,  7,  6,  6,   6,  'INST-001'),
(8,  8,  9,  2,   2,  'INST-001'),
(9,  9,  13, 4,   0,  'INST-002'),
(10, 10, 11, 5,   5,  'INST-002');

-- =====================================================
-- 13. SINCRONIZAR SECUENCIAS  (NO OLVIDAR)
-- =====================================================
-- `OVERRIDING SYSTEM VALUE` inserta ids explicitos pero NO avanza la
-- secuencia de la columna. El TRUNCATE ... RESTART IDENTITY la dejo en 1,
-- asi que sin este bloque el siguiente POST intentaria generar ticket_id = 1,
-- chocaria con el id 1 ya insertado y responderia HTTP 500 por
-- UniqueViolation. Este bloque deja cada secuencia en MAX(id).

SELECT setval(pg_get_serial_sequence('departamento',           'departamento_id'),           COALESCE((SELECT MAX(departamento_id)           FROM departamento),           1));
SELECT setval(pg_get_serial_sequence('departamento_encargado', 'departamento_encargado_id'), COALESCE((SELECT MAX(departamento_encargado_id) FROM departamento_encargado), 1));
SELECT setval(pg_get_serial_sequence('sede',                   'sede_id'),                   COALESCE((SELECT MAX(sede_id)                   FROM sede),                   1));
SELECT setval(pg_get_serial_sequence('stock_sede',             'stock_sede_id'),             COALESCE((SELECT MAX(stock_sede_id)             FROM stock_sede),             1));
SELECT setval(pg_get_serial_sequence('rol',                    'rol_id'),                    COALESCE((SELECT MAX(rol_id)                    FROM rol),                    1));
SELECT setval(pg_get_serial_sequence('usuario',                'usuario_id'),                COALESCE((SELECT MAX(usuario_id)                FROM usuario),                1));
SELECT setval(pg_get_serial_sequence('categoria',              'categoria_id'),              COALESCE((SELECT MAX(categoria_id)              FROM categoria),              1));
SELECT setval(pg_get_serial_sequence('producto',               'producto_id'),               COALESCE((SELECT MAX(producto_id)               FROM producto),               1));
SELECT setval(pg_get_serial_sequence('movimiento_inventario', 'movimiento_id'),             COALESCE((SELECT MAX(movimiento_id)             FROM movimiento_inventario), 1));
SELECT setval(pg_get_serial_sequence('prioridad',              'prioridad_id'),              COALESCE((SELECT MAX(prioridad_id)              FROM prioridad),              1));
SELECT setval(pg_get_serial_sequence('estado_ticket',          'estado_id'),                 COALESCE((SELECT MAX(estado_id)                 FROM estado_ticket),          1));
SELECT setval(pg_get_serial_sequence('ticket',                 'ticket_id'),                 COALESCE((SELECT MAX(ticket_id)                 FROM ticket),                 1));
SELECT setval(pg_get_serial_sequence('detalle_ticket',         'detalle_ticket_id'),         COALESCE((SELECT MAX(detalle_ticket_id)         FROM detalle_ticket),         1));
SELECT setval(pg_get_serial_sequence('proveedor',              'proveedor_id'),              COALESCE((SELECT MAX(proveedor_id)              FROM proveedor),              1));
SELECT setval(pg_get_serial_sequence('orden_compra',           'orden_compra_id'),           COALESCE((SELECT MAX(orden_compra_id)           FROM orden_compra),           1));
SELECT setval(pg_get_serial_sequence('detalle_orden_compra',   'detalle_orden_compra_id'),   COALESCE((SELECT MAX(detalle_orden_compra_id)   FROM detalle_orden_compra),   1));
SELECT setval(pg_get_serial_sequence('factura_compra',         'factura_compra_id'),         COALESCE((SELECT MAX(factura_compra_id)         FROM factura_compra),         1));

-- =====================================================
-- REPARTO A TENANTS
-- =====================================================
-- Los esquemas y las tablas ya existen: los creo 01_esquema.sql. Este
-- bloque copia los datos de control a cada tenant, resetea sus secuencias,
-- marca la version objetivo y verifica el cuadre. `control` se vacia al
-- final (seccion FASE 3), conservando la topologia y el contexto global.

CREATE OR REPLACE FUNCTION pg_temp.resetear_identidades(p_esq text)
RETURNS void
LANGUAGE plpgsql
AS $reset$
DECLARE
    pares text[] := ARRAY[
        'sede:sede_id',
        'stock_sede:stock_sede_id',
        'departamento:departamento_id',
        'departamento_encargado:departamento_encargado_id',
        'rol:rol_id',
        'usuario:usuario_id',
        'categoria:categoria_id',
        'producto:producto_id',
        'movimiento_inventario:movimiento_id',
        'prioridad:prioridad_id',
        'estado_ticket:estado_id',
        'ticket:ticket_id',
        'detalle_ticket:detalle_ticket_id',
        'historial_transicion_ticket:historial_transicion_id',
        'historial_transicion_producto:historial_producto_id',
        'historial_transicion_categoria:historial_categoria_id',
        'orden_compra:orden_compra_id',
        'detalle_orden_compra:detalle_orden_compra_id',
        'factura_compra:factura_compra_id',
        'orden_compra_ticket:orden_compra_ticket_id'
    ];
    par text;
    v_tabla text;
    v_columna text;
    v_registro text;
BEGIN
    FOREACH par IN ARRAY pares LOOP
        v_tabla := split_part(par, ':', 1);
        v_columna := split_part(par, ':', 2);
        v_registro := format('%I.%I', p_esq, v_tabla);
        IF to_regclass(v_registro) IS NULL THEN
            CONTINUE;
        END IF;
        EXECUTE format(
            'SELECT setval(pg_get_serial_sequence(%L, %L), '
            'COALESCE((SELECT max(%I) FROM %I.%I), 0) + 1, false)',
            v_registro, v_columna, v_columna, p_esq, v_tabla
        );
    END LOOP;
END;
$reset$;

DO $construccion$
DECLARE
    v_version_objetivo constant text := '026.0';
    v_institucion_id text;
    v_esquema text;
    v_plantilla text;
    v_conteo integer;
    v_esperado integer;
    v_mapa_esperado integer;
    v_obtenido integer;
BEGIN
    -- Preflight: los tenants ya deben existir (los creo 01_).
    FOR v_institucion_id IN SELECT institucion_id FROM control.institucion ORDER BY institucion_id LOOP
        v_esquema := pg_temp.nombre_esquema_tenant(v_institucion_id);
        IF to_regnamespace(v_esquema) IS NULL THEN
            RAISE EXCEPTION '02: falta el esquema tenant % (01_ no lo creo).', v_esquema;
        END IF;
    END LOOP;

    -- FASE 1: UN ESQUEMA TENANT POR INSTITUCION (estructura + datos)
    -------------------------------------------------------------------------
    FOR v_institucion_id IN SELECT institucion_id FROM control.institucion ORDER BY institucion_id LOOP
        v_esquema := pg_temp.nombre_esquema_tenant(v_institucion_id);


        -- (1.2) Registro institucional espejo y catalogos replicados.
        --       `rol` excluye Superadmin (vive solo en control); D-4 replica
        --       rol/prioridad/estado_ticket en cada tenant.
        -- Espejo tenant de dos columnas (Feature 012): el canonico de control ya
        -- no cabe en un `SELECT *` (porta `rut`/`direccion`/`activo`), asi que la
        -- copia nombra exactamente las columnas del espejo aprobado.
        EXECUTE format(
            'INSERT INTO %I.institucion (institucion_id, nombre) '
            'SELECT institucion_id, nombre FROM control.institucion WHERE institucion_id = $1',
            v_esquema
        ) USING v_institucion_id;
        EXECUTE format(
            'INSERT INTO %I.rol OVERRIDING SYSTEM VALUE '
            'SELECT * FROM control.rol WHERE nombre_rol <> ''Superadmin''', v_esquema
        );
        EXECUTE format('INSERT INTO %1$I.prioridad OVERRIDING SYSTEM VALUE SELECT * FROM control.prioridad', v_esquema);
        EXECUTE format('INSERT INTO %1$I.estado_ticket OVERRIDING SYSTEM VALUE SELECT * FROM control.estado_ticket', v_esquema);
        -- Feature 020: replica local del catalogo global con el MISMO id. El
        -- `proveedor_id` del tenant NO es identity, asi que no lleva OVERRIDING.
        EXECUTE format('INSERT INTO %1$I.proveedor SELECT * FROM control.proveedor', v_esquema);

        -- (1.3) Datos organizacionales: sede, departamento y usuario.
        EXECUTE format(
            'INSERT INTO %I.sede OVERRIDING SYSTEM VALUE '
            'SELECT * FROM control.sede WHERE institucion_id = $1', v_esquema
        ) USING v_institucion_id;
        EXECUTE format(
            'INSERT INTO %I.departamento OVERRIDING SYSTEM VALUE '
            'SELECT * FROM control.departamento WHERE institucion_id = $1', v_esquema
        ) USING v_institucion_id;
        -- usuario se asigna por el departamento; el Superadmin no se replica.
        EXECUTE format(
            'INSERT INTO %I.usuario OVERRIDING SYSTEM VALUE '
            'SELECT u.* FROM control.usuario u '
            'JOIN control.departamento d ON d.departamento_id = u.departamento_id '
            'WHERE d.institucion_id = $1 '
            'AND u.rol_id NOT IN (SELECT rol_id FROM control.rol WHERE nombre_rol = ''Superadmin'')',
            v_esquema
        ) USING v_institucion_id;
        -- Encargados: por la institucion de su departamento.
        EXECUTE format(
            'INSERT INTO %I.departamento_encargado OVERRIDING SYSTEM VALUE '
            'SELECT de.* FROM control.departamento_encargado de '
            'JOIN control.departamento d ON d.departamento_id = de.departamento_id '
            'WHERE d.institucion_id = $1', v_esquema
        ) USING v_institucion_id;

        -- (1.4) Catalogo y stock, con institucion_id directo.
        FOREACH v_plantilla IN ARRAY ARRAY['categoria', 'producto', 'stock_sede'] LOOP
            EXECUTE format(
                'INSERT INTO %I.%I OVERRIDING SYSTEM VALUE '
                'SELECT * FROM control.%I WHERE institucion_id = $1',
                v_esquema, v_plantilla, v_plantilla
            ) USING v_institucion_id;
        END LOOP;

        -- (1.5) Movimientos por el saldo de su sede y tickets/detalles
        --       (institucion directa). `stock_sede_id` es obligatorio desde la
        --       Feature 026: ya no existe el enlace por `inventario`.
        EXECUTE format(
            'INSERT INTO %I.movimiento_inventario OVERRIDING SYSTEM VALUE '
            'SELECT m.* FROM control.movimiento_inventario m '
            'JOIN control.stock_sede s ON s.stock_sede_id = m.stock_sede_id '
            'WHERE s.institucion_id = $1', v_esquema
        ) USING v_institucion_id;
        FOREACH v_plantilla IN ARRAY ARRAY['ticket', 'detalle_ticket'] LOOP
            EXECUTE format(
                'INSERT INTO %I.%I OVERRIDING SYSTEM VALUE '
                'SELECT * FROM control.%I WHERE institucion_id = $1',
                v_esquema, v_plantilla, v_plantilla
            ) USING v_institucion_id;
        END LOOP;

        -- (1.6) Secuencias continuas (la copia con OVERRIDING no las avanza).
        PERFORM pg_temp.resetear_identidades(v_esquema);

        -- (1.7) Version objetivo SOLO al final, tras poblar el tenant.
        EXECUTE format(
            'INSERT INTO %I.version_esquema (version) VALUES (%L)',
            v_esquema, v_version_objetivo
        );

        -- (1.8) Verificacion local antes de continuar (fail-closed).
        --       (1.8.1) Espejo institucional exactamente una fila.
        EXECUTE format('SELECT count(*) FROM %I.institucion', v_esquema) INTO v_obtenido;
        IF v_obtenido <> 1 THEN
            RAISE EXCEPTION '02: espejo institucion en % -> % (esperado 1).', v_esquema, v_obtenido;
        END IF;
        --       (1.8.2) Una unica fila de version objetivo.
        EXECUTE format(
            'SELECT count(*) FROM %I.version_esquema WHERE version = %L', v_esquema, v_version_objetivo
        ) INTO v_obtenido;
        IF v_obtenido <> 1 THEN
            RAISE EXCEPTION '02: % no tiene una fila de version % (tiene %).', v_esquema, v_version_objetivo, v_obtenido;
        END IF;
        --       (1.8.3) Conteos de negocio == los de control para esta institucion.
        EXECUTE format('SELECT count(*) FROM control.departamento WHERE institucion_id = $1', v_esquema)
            INTO v_esperado USING v_institucion_id;
        EXECUTE format('SELECT count(*) FROM %I.departamento', v_esquema) INTO v_obtenido;
        IF v_esperado <> v_obtenido THEN
            RAISE EXCEPTION '02: % departamento(s) esperados en %, obtenidos %.', v_esperado, v_esquema, v_obtenido;
        END IF;
        EXECUTE format('SELECT count(*) FROM control.sede WHERE institucion_id = $1', v_esquema)
            INTO v_esperado USING v_institucion_id;
        EXECUTE format('SELECT count(*) FROM %I.sede', v_esquema) INTO v_obtenido;
        IF v_esperado <> v_obtenido THEN
            RAISE EXCEPTION '02: % sede(s) esperadas en %, obtenidas %.', v_esperado, v_esquema, v_obtenido;
        END IF;
        --       (1.8.3b) Replica exacta del catalogo global de proveedores: mismo
        --       numero de filas y los MISMOS `proveedor_id` que control.
        SELECT count(*) INTO v_esperado FROM control.proveedor;
        EXECUTE format('SELECT count(*) FROM %I.proveedor', v_esquema) INTO v_obtenido;
        IF v_esperado <> v_obtenido THEN
            RAISE EXCEPTION '02: % proveedor(es) esperados en %, obtenidos %.', v_esperado, v_esquema, v_obtenido;
        END IF;
        EXECUTE format(
            'SELECT count(*) FROM %1$I.proveedor t '
            'LEFT JOIN control.proveedor c ON c.proveedor_id = t.proveedor_id '
            'WHERE c.proveedor_id IS NULL', v_esquema
        ) INTO v_obtenido;
        IF v_obtenido <> 0 THEN
            RAISE EXCEPTION '02: % proveedor(es) con id distinto al catalogo global en %.', v_obtenido, v_esquema;
        END IF;
        --       (1.8.4) Ningun usuario huerfano (todo usuario tiene departamento).
        EXECUTE format(
            'SELECT count(*) FROM %I.usuario u '
            'LEFT JOIN %I.departamento d ON d.departamento_id = u.departamento_id '
            'WHERE d.departamento_id IS NULL', v_esquema, v_esquema
        ) INTO v_obtenido;
        IF v_obtenido <> 0 THEN
            RAISE EXCEPTION '02: % usuario(s) huerfano(s) en %.', v_obtenido, v_esquema;
        END IF;
        --       (1.8.5) Stock: el tenant replica exactamente los saldos de su
        --       institucion y todo movimiento apunta a un saldo copiado.
        EXECUTE format('SELECT count(*) FROM control.stock_sede WHERE institucion_id = $1', v_esquema)
            INTO v_esperado USING v_institucion_id;
        EXECUTE format('SELECT count(*) FROM %I.stock_sede', v_esquema) INTO v_obtenido;
        IF v_esperado <> v_obtenido THEN
            RAISE EXCEPTION '02: % saldo(s) esperados en %, obtenidos %.', v_esperado, v_esquema, v_obtenido;
        END IF;
        EXECUTE format(
            'SELECT count(*) FROM control.movimiento_inventario m '
            'JOIN control.stock_sede s ON s.stock_sede_id = m.stock_sede_id '
            'WHERE s.institucion_id = $1', v_esquema
        ) INTO v_esperado USING v_institucion_id;
        EXECUTE format('SELECT count(*) FROM %I.movimiento_inventario', v_esquema) INTO v_obtenido;
        IF v_esperado <> v_obtenido THEN
            RAISE EXCEPTION '02: % movimiento(s) esperados en %, obtenidos %.', v_esperado, v_esquema, v_obtenido;
        END IF;
        EXECUTE format(
            'SELECT count(*) FROM %I.movimiento_inventario WHERE stock_sede_id IS NULL', v_esquema
        ) INTO v_obtenido;
        IF v_obtenido <> 0 THEN
            RAISE EXCEPTION '02: % movimiento(s) sin stock_sede en %.', v_obtenido, v_esquema;
        END IF;

        --       (1.8.6) La tabla legada `inventario` ya no existe en el tenant.
        IF to_regclass(format('%I.inventario', v_esquema)) IS NOT NULL THEN
            RAISE EXCEPTION '02: la tabla legada inventario sigue en %.', v_esquema;
        END IF;
    END LOOP;

    -------------------------------------------------------------------------
    -- IDENTIDAD GLOBAL DE PRUEBA (Superadmin)
    -------------------------------------------------------------------------
    -- El Superadmin no pertenece a un tenant de negocio: vive en `control` y
    -- se enruta mediante el esquema reservado `control`. La institucion y el
    -- departamento administrativos satisfacen las FK NOT NULL sin contaminar
    -- ninguno de los tenants institucionales.
    INSERT INTO control.institucion (
        institucion_id, nombre, rut, direccion, activo
    ) VALUES (
        'CTRL-SAAS', 'CompuStock SaaS', NULL, 'Esquema de control', TRUE
    )
    ON CONFLICT (institucion_id) DO NOTHING;

    INSERT INTO control.departamento (
        nombre_dep, descripcion, institucion_id, sede_id, activo
    )
    SELECT
        'Administracion SaaS',
        'Departamento administrativo del esquema de control',
        'CTRL-SAAS',
        NULL,
        TRUE
    WHERE NOT EXISTS (
        SELECT 1
        FROM control.departamento
        WHERE institucion_id = 'CTRL-SAAS'
    );

    INSERT INTO control.usuario (
        usuario_id, nombre, apellido, correo, departamento_id, rol_id, sede_id
    ) OVERRIDING SYSTEM VALUE
    SELECT
        COALESCE((SELECT max(usuario_id) FROM control.usuario), 0) + 1,
        'Superadmin',
        'Sistema',
        'superadmin.test+clerk_test@example.com',
        d.departamento_id,
        r.rol_id,
        NULL
    FROM control.departamento d
    JOIN control.rol r ON r.nombre_rol = 'Superadmin'
    WHERE d.institucion_id = 'CTRL-SAAS'
      AND NOT EXISTS (
          SELECT 1
          FROM control.usuario
          WHERE correo = 'superadmin.test+clerk_test@example.com'
      );

    -------------------------------------------------------------------------
    -- GUARDAS GLOBALES DE STOCK (Feature 026), antes de vaciar `control`
    -------------------------------------------------------------------------
    SELECT count(*) INTO v_obtenido FROM control.stock_sede;
    IF v_obtenido <> 14 THEN
        RAISE EXCEPTION '02: control.stock_sede tiene % fila(s) (esperadas 14).', v_obtenido;
    END IF;
    SELECT count(*) INTO v_obtenido FROM control.stock_sede WHERE institucion_id = 'INST-001';
    IF v_obtenido <> 10 THEN
        RAISE EXCEPTION '02: INST-001 tiene % saldo(s) (esperados 10).', v_obtenido;
    END IF;
    SELECT count(*) INTO v_obtenido FROM control.stock_sede WHERE institucion_id = 'INST-002';
    IF v_obtenido <> 4 THEN
        RAISE EXCEPTION '02: INST-002 tiene % saldo(s) (esperados 4).', v_obtenido;
    END IF;

    SELECT count(*) INTO v_obtenido FROM control.movimiento_inventario;
    IF v_obtenido <> 3 THEN
        RAISE EXCEPTION '02: control.movimiento_inventario tiene % fila(s) (esperadas 3).', v_obtenido;
    END IF;
    SELECT count(*) INTO v_obtenido FROM control.movimiento_inventario WHERE stock_sede_id IS NULL;
    IF v_obtenido <> 0 THEN
        RAISE EXCEPTION '02: % movimiento(s) sin stock_sede en control.', v_obtenido;
    END IF;

    SELECT stock_actual INTO v_obtenido FROM control.stock_sede WHERE stock_sede_id = 8;
    IF v_obtenido <> 45 THEN
        RAISE EXCEPTION '02: saldo 8 tiene % (esperado 45).', v_obtenido;
    END IF;
    SELECT stock_actual INTO v_obtenido FROM control.stock_sede WHERE stock_sede_id = 9;
    IF v_obtenido <> 12 THEN
        RAISE EXCEPTION '02: saldo 9 tiene % (esperado 12).', v_obtenido;
    END IF;

    SELECT s.stock_actual - coalesce(sum(
               CASE m.tipo_movimiento WHEN 'ENTRADA' THEN m.cantidad ELSE -m.cantidad END
           ), 0)
      INTO v_obtenido
      FROM control.stock_sede s
      LEFT JOIN control.movimiento_inventario m ON m.stock_sede_id = s.stock_sede_id
     WHERE s.stock_sede_id = 8
     GROUP BY s.stock_actual;
    IF v_obtenido <> 35 THEN
        RAISE EXCEPTION '02: apertura del saldo 8 = % (esperada 35).', v_obtenido;
    END IF;
    SELECT s.stock_actual - coalesce(sum(
               CASE m.tipo_movimiento WHEN 'ENTRADA' THEN m.cantidad ELSE -m.cantidad END
           ), 0)
      INTO v_obtenido
      FROM control.stock_sede s
      LEFT JOIN control.movimiento_inventario m ON m.stock_sede_id = s.stock_sede_id
     WHERE s.stock_sede_id = 9
     GROUP BY s.stock_actual;
    IF v_obtenido <> 6 THEN
        RAISE EXCEPTION '02: apertura del saldo 9 = % (esperada 6).', v_obtenido;
    END IF;
    -------------------------------------------------------------------------
    -- FASE 2: MAPA `correo -> esquema` DE TODOS LOS USUARIOS LOCALES
    -------------------------------------------------------------------------
    -- La identidad Superadmin se asocia al esquema reservado `control` (stack
    -- 4/7); el resto apunta a su tenant derivado. Se puebla ANTES de vaciar
    -- `control.usuario`.
    -- Feature 017: todos los usuarios de la semilla tienen identidad Clerk
    -- preexistente, asi que su mapa nace en `aceptada` (D-1); no hay invitacion
    -- pendiente, por lo que `invitacion_id` y sus timestamps quedan nulos.
    SELECT count(*) INTO v_mapa_esperado FROM control.usuario;

    INSERT INTO control.mapa_usuario_esquema (
        correo, institucion_id, nombre_esquema, activo, estado_invitacion
    )
    SELECT u.correo,
           d.institucion_id,
           CASE WHEN r.nombre_rol = 'Superadmin'
                THEN 'control'
                ELSE pg_temp.nombre_esquema_tenant(d.institucion_id)
           END,
           TRUE,
           'aceptada'
    FROM control.usuario u
    JOIN control.departamento d ON d.departamento_id = u.departamento_id
    JOIN control.rol r ON r.rol_id = u.rol_id
    ON CONFLICT (correo) DO NOTHING;

    -------------------------------------------------------------------------
    -- FASE 3: DEJAR `control` COMO CONTEXTO GLOBAL
    -------------------------------------------------------------------------
    -- Se conservan `institucion` (registro canonico, destino de la FK del mapa),
    -- `rol` (incluido Superadmin) y `mapa_usuario_esquema`. Se VACIAN las tablas
    -- de negocio tras copiarlas: su lugar es cada tenant. El orden respeta las FK.
    -- Excepcion de la Feature 013: `estado_ticket` conserva la fila `Anulado`
    -- (presencia obligatoria en toda instalacion; stack.md Feature 013); es el espejo
    -- exacto del estado que el backend espera encontrar en `control` de una
    -- instalacion limpia. El resto del catalogo (y `prioridad`) se vacia como antes.
    -- Feature 020: las compras no se siembran; el catalogo de proveedores SI se
    -- conserva (es global y lo usan todas las instituciones).
    -- Feature 021: el plan de cobertura tampoco se siembra y se borra antes de
    -- `detalle_orden_compra`, `ticket` y `producto` por sus FKs compuestas.
    DELETE FROM control.orden_compra_ticket;
    DELETE FROM control.factura_compra;
    DELETE FROM control.detalle_orden_compra;
    DELETE FROM control.orden_compra;
    DELETE FROM control.detalle_ticket;
    DELETE FROM control.movimiento_inventario;
    DELETE FROM control.stock_sede;
    DELETE FROM control.ticket;
    DELETE FROM control.departamento_encargado;
    DELETE FROM control.producto;
    DELETE FROM control.categoria;
    -- Se conserva exclusivamente la identidad global de prueba; los usuarios
    -- institucionales ya fueron copiados a su tenant correspondiente.
    DELETE FROM control.usuario
    WHERE rol_id NOT IN (
        SELECT rol_id FROM control.rol WHERE nombre_rol = 'Superadmin'
    );
    DELETE FROM control.departamento
    WHERE institucion_id <> 'CTRL-SAAS';
    DELETE FROM control.sede;
    DELETE FROM control.prioridad;
    DELETE FROM control.estado_ticket WHERE nombre <> 'Anulado';

    -- Version objetivo de control (una sola fila vigente).
    IF EXISTS (SELECT 1 FROM control.version_esquema) THEN
        UPDATE control.version_esquema
        SET version = v_version_objetivo, actualizada_en = CURRENT_TIMESTAMP;
    ELSE
        INSERT INTO control.version_esquema (version) VALUES (v_version_objetivo);
    END IF;

    -------------------------------------------------------------------------
    -- FASE 4: VERIFICACION GLOBAL (fail-closed)
    -------------------------------------------------------------------------
    SELECT count(*) INTO v_conteo
    FROM control.version_esquema WHERE version = v_version_objetivo;
    IF v_conteo <> 1 THEN
        RAISE EXCEPTION '02: control no tiene una unica fila de version %.', v_version_objetivo;
    END IF;

    FOR v_institucion_id IN
        SELECT institucion_id
        FROM control.institucion
        WHERE institucion_id <> 'CTRL-SAAS'
        ORDER BY institucion_id
    LOOP
        v_esquema := pg_temp.nombre_esquema_tenant(v_institucion_id);
        IF to_regclass(format('%I.version_esquema', v_esquema)) IS NULL THEN
            RAISE EXCEPTION '02: el tenant % no existe.', v_esquema;
        END IF;
        EXECUTE format(
            'SELECT count(*) FROM %I.version_esquema WHERE version = %L', v_esquema, v_version_objetivo
        ) INTO v_conteo;
        IF v_conteo <> 1 THEN
            RAISE EXCEPTION '02: el tenant % no tiene una unica fila de version %.', v_esquema, v_version_objetivo;
        END IF;
    END LOOP;

    RAISE NOTICE '02: semilla y tenants completados. control + tenants en version %; datos distribuidos por institucion.', v_version_objetivo;

    -- Chequeo final de control: solo queda la identidad global Superadmin.
    IF (
        SELECT count(*)
        FROM control.usuario u
        JOIN control.rol r ON r.rol_id = u.rol_id
        WHERE r.nombre_rol = 'Superadmin'
    ) <> 1
    OR (SELECT count(*) FROM control.usuario) <> 1 THEN
        RAISE EXCEPTION '02: control.usuario debe conservar solo el Superadmin.';
    END IF;
    IF (SELECT count(*) FROM control.ticket) <> 0 OR (SELECT count(*) FROM control.detalle_ticket) <> 0 THEN
        RAISE EXCEPTION '02: quedaron tickets en control.';
    END IF;
    IF (SELECT count(*) FROM control.estado_ticket) <> 1 THEN
        RAISE EXCEPTION '02: control.estado_ticket debe conservar solo Anulado.';
    END IF;
    IF (SELECT count(*) FROM control.mapa_usuario_esquema) <> v_mapa_esperado THEN
        RAISE EXCEPTION '02: el mapa de usuarios no coincide con los usuarios sembrados.';
    END IF;
    -- Feature 017: la semilla solo vincula identidades Clerk existentes.
    IF EXISTS (
        SELECT 1 FROM control.mapa_usuario_esquema
        WHERE estado_invitacion IS DISTINCT FROM 'aceptada'
    ) THEN
        RAISE EXCEPTION '02: el mapa sembrado debe nacer en estado_invitacion = aceptada.';
    END IF;
    IF (SELECT count(*) FROM control.registro_motivo_constancia) <> 0 THEN
        RAISE EXCEPTION '02: control.registro_motivo_constancia debe quedar vacia.';
    END IF;
    -- Feature 020: control.proveedor SOBREVIVE a la Fase 3 (catalogo global) y
    -- las tres tablas de compras deben quedar vacias en control.
    IF (SELECT count(*) FROM control.proveedor) <> 3 THEN
        RAISE EXCEPTION '02: control.proveedor debe conservar los 3 proveedores sembrados.';
    END IF;
    IF (SELECT count(*) FROM control.orden_compra) <> 0
       OR (SELECT count(*) FROM control.detalle_orden_compra) <> 0
       OR (SELECT count(*) FROM control.factura_compra) <> 0
       OR (SELECT count(*) FROM control.orden_compra_ticket) <> 0 THEN
        RAISE EXCEPTION '02: las compras no deben quedar sembradas en control.';
    END IF;
    -- Feature 014: la semilla no fabrica transiciones de catalogo.
    IF (SELECT count(*) FROM control.historial_transicion_producto) <> 0
       OR (SELECT count(*) FROM control.historial_transicion_categoria) <> 0 THEN
        RAISE EXCEPTION '02: los historiales del catalogo deben quedar vacios.';
    END IF;
    IF EXISTS (SELECT 1 FROM control.categoria WHERE activo IS NOT TRUE)
       OR EXISTS (SELECT 1 FROM control.producto WHERE activo IS NOT TRUE) THEN
        RAISE EXCEPTION '02: el catalogo sembrado debe nacer activo.';
    END IF;
END;
$construccion$;

COMMIT;
