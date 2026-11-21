# Pruebas de compatibilidad — pendiente

Carpeta reservada para las pruebas **no funcionales de compatibilidad** del
frontend: navegadores, versiones, dispositivos y tamaños de pantalla.

## Estado actual

**Sin tests automatizados.** El proyecto cubre compatibilidad de forma parcial:

- La suite corre en Chromium mediante Karma. En esta máquina solo hay Edge, así
  que el launcher se apunta con:

  ```powershell
  $env:CHROME_BIN = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
  ```

- Los recorridos de cierre se hacen en **4200** (dev server) y **8080**
  (build de producción servido por nginx), que es la misma base de código en
  dos formas de servirla, no en dos navegadores.

## Brecha

Solo hay **un motor** verificado. Firefox, Safari y los navegadores móviles no
están en la matriz de pruebas, y tampoco hay verificación de responsive más allá
de la ventana de escritorio usada en los recorridos.

## Qué debería entrar aquí

1. Ejecución de la suite en **Firefox** (`ChromeHeadlessFirefox`) y, si hay
   máquina disponible, en **Safari/WebKit**.
2. Pruebas de **responsive** en los cortes de 1366 px (referencia actual),
   tablet y móvil.
3. Verificación de que el bundle de producción no usa APIs no soportadas por
   los navegadores objetivo (`build` con los targets del `angular.json`).
4. Comportamiento del borde nginx con cabeceras y compresión en navegadores
   antiguos.

## Relación con la deuda técnica

La ausencia de matriz de navegadores y de CI es el hallazgo **DT-07** de
`docs/spec/deuda-tecnica.md` (sin CI ni auditoría automatizada de dependencias):
sin pipeline, la matriz de compatibilidad no se puede sostener en el tiempo.
