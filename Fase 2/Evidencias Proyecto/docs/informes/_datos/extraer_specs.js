/* Extrae describe/it de los specs de Angular con el AST de TypeScript.
 *
 * Uso:
 *   node docs/informes/_datos/extraer_specs.js
 *
 * Genera frontend-specs.json junto a este script. No ejecuta Karma: solo
 * enumera los casos estáticos. Los 21 casos generados por bucles se expanden
 * en _generar_planilla_pruebas.py.
 */
const fs = require('fs');
const path = require('path');

const PROYECTO = path.resolve(__dirname, '../../..');
const TS = require(path.join(PROYECTO, 'frontend/node_modules/typescript'));
const SRC = path.join(PROYECTO, 'frontend/src');
const SALIDA = path.join(__dirname, 'frontend-specs.json');

function archivosSpec(dir) {
  const salida = [];
  for (const entrada of fs.readdirSync(dir, { withFileTypes: true })) {
    const ruta = path.join(dir, entrada.name);
    if (entrada.isDirectory()) salida.push(...archivosSpec(ruta));
    else if (entrada.name.endsWith('.spec.ts')) salida.push(ruta);
  }
  return salida.sort();
}

function titulo(nodo) {
  if (!nodo) return '';
  if (TS.isStringLiteral(nodo) || TS.isNoSubstitutionTemplateLiteral(nodo)) return nodo.text;
  if (TS.isTemplateExpression(nodo)) {
    let texto = nodo.head.text;
    for (const span of nodo.templateSpans) {
      texto += '${' + span.expression.getText() + '}' + span.literal.text;
    }
    return texto;
  }
  return nodo.getText();
}

function comentariosPrevios(sourceFile, nodo) {
  const rangos = TS.getLeadingCommentRanges(sourceFile.text, nodo.getFullStart()) || [];
  return rangos.map((r) => sourceFile.text.slice(r.pos, r.end)).join('\n');
}

function contarExpectativas(nodo) {
  let total = 0;
  let expectNone = 0;
  function visitar(n) {
    if (TS.isCallExpression(n)) {
      const texto = n.expression.getText();
      if (texto === 'expect' || texto.endsWith('.expect')) total += 1;
      if (texto.endsWith('expectNone')) expectNone += 1;
    }
    TS.forEachChild(n, visitar);
  }
  visitar(nodo);
  return { expect: total, expectNone };
}

function extraer(archivo) {
  const texto = fs.readFileSync(archivo, 'utf8');
  const sourceFile = TS.createSourceFile(archivo, texto, TS.ScriptTarget.Latest, true);
  const relativos = path.relative(PROYECTO, archivo).replace(/\\/g, '/');
  const casos = [];

  function visitar(nodo, pilaDescribe) {
    if (TS.isCallExpression(nodo)) {
      const nombre = nodo.expression.getText();
      if (nombre === 'describe' && nodo.arguments.length >= 2) {
        const tituloDescribe = titulo(nodo.arguments[0]);
        visitar(nodo.arguments[1], [...pilaDescribe, tituloDescribe]);
        return;
      }
      if (['it', 'fit', 'xit'].includes(nombre) && nodo.arguments.length >= 1) {
        const pos = sourceFile.getLineAndCharacterOfPosition(nodo.getStart(sourceFile));
        const comentario = comentariosPrevios(sourceFile, nodo);
        const tituloCaso = titulo(nodo.arguments[0]);
        const { expect, expectNone } = nodo.arguments.length >= 2
          ? contarExpectativas(nodo.arguments[1])
          : { expect: 0, expectNone: 0 };
        const textoAc = `${tituloCaso}\n${pilaDescribe.join('\n')}\n${comentario}`;
        const ac = [...new Set((textoAc.match(/AC-\d+/g) || []))].sort();
        casos.push({
          archivo: relativos,
          linea: pos.line + 1,
          suite: pilaDescribe,
          titulo: tituloCaso,
          nombreCompleto: [...pilaDescribe, tituloCaso].join(' › '),
          expect,
          expectNone,
          ac,
          comentario: comentario.replace(/\r/g, '').trim(),
        });
        return;
      }
    }
    TS.forEachChild(nodo, (hijo) => visitar(hijo, pilaDescribe));
  }

  visitar(sourceFile, []);
  return casos;
}

const archivos = archivosSpec(SRC);
const todos = [];
for (const archivo of archivos) {
  todos.push(...extraer(archivo));
}
fs.writeFileSync(SALIDA, JSON.stringify(todos, null, 2), 'utf8');
console.log(JSON.stringify({ archivos: archivos.length, casos: todos.length, salida: SALIDA }, null, 2));
