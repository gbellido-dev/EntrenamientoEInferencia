# Enseñar al ordenador a localizar objetos

## Tu proyecto empieza vacío

Primero decide **qué quieres detectar**. Crea un proyecto y añade tus propias etiquetas, una a una. Pueden ser una o varias; no hay etiquetas obligatorias predefinidas.

Una etiqueta es el nombre de un tipo de objeto. Un rectángulo indica dónde está uno de esos objetos en la imagen. Si aparecen tres objetos, dibuja tres rectángulos y asigna a cada uno su etiqueta.

**Imagen → rectángulos y etiquetas → entrenamiento → evaluación → modelo exportado → cámara.**

## Preparar ejemplos

1. Recoge fotografías variadas del problema elegido.
2. Importa las fotos y asigna un grupo a las que están relacionadas por sesión, objeto o muestra.
3. Elige una etiqueta en el selector y arrastra una caja ajustada alrededor del objeto.
4. Marca todos los objetos de las etiquetas del proyecto, no solo el más grande.
5. Corrige las etiquetas y los rectángulos. Puedes borrar y deshacer.
6. Confirma la revisión. Si no hay ninguno de tus objetos, usa «Confirmar sin objetos».

También puedes pulsar el área vacía del editor para seleccionar una o varias fotos, o arrastrarlas sobre ella. Si todavía no hay proyecto, se pedirá dónde guardarlo. Solo se importan los archivos elegidos; volver a seleccionar una foto existente conserva sus anotaciones.

El selector «Conjunto» recuerda tu última elección para las siguientes fotos sin asignar, también al avanzar automáticamente después de dibujar un rectángulo. Las fotos que ya tienen conjunto conservan su valor; verlas no cambia tu última elección. Si eliges «Automático / Otro» expresamente para una foto, esa elección también se conserva. La preferencia se guarda con el proyecto.

Para cambiar varias fotos a otro conjunto, abre «Todas». Marca sus casillas o selecciona filas con Ctrl+clic (fotos sueltas) y Shift+clic (un tramo). El contador indica cuántas se moverán. Elige el destino bajo la lista y pulsa «Mover seleccionadas». Si hay casillas marcadas, se usan esas fotos; en caso contrario se usan las filas resaltadas. «Limpiar selección» desmarca todo. Los rectángulos y las etiquetas de las fotos se conservan.

Una foto sin revisar no es lo mismo que una foto revisada sin objetos. Las fotos pendientes se omiten para no dar respuestas incorrectas al modelo.

Los ejemplos de la demostración son opcionales y pertenecen a otro proyecto. No necesitas incluir sus etiquetas ni sus imágenes en tu trabajo.

## Etiquetar fotos completas en bloque

En «Todas», selecciona las fotos con casillas, Ctrl+clic o Shift+clic y pulsa «Etiquetar fotos completas…». Elige una etiqueta: se crea una sola anotación que ocupa toda cada fotografía y se confirma su revisión. Puedes repetir con otras fotos y otra etiqueta. El conjunto y el grupo de cada foto se conservan; las fotos descartadas siguen descartadas. Si ya había otras anotaciones, se pide confirmación antes de sustituirlas. Puedes abrir una foto y usar «Deshacer» durante la sesión para recuperar sus anotaciones anteriores.

Úsalo con fotos donde un único objeto ocupa prácticamente toda la imagen. Si quieres que después encuentre varios objetos pequeños dentro de una escena, enseña sus ubicaciones con recuadros ajustados: marcar toda la foto no enseña dónde termina cada objeto.

## Descargar ejemplos desde Kaggle

Pulsa «Descargar de Kaggle…» y pega la dirección de un dataset o su identificador `propietario/dataset`. Elige la carpeta base y descarga. Puedes usar cualquier dataset; la herramienta no presupone caras, células ni otras clases. También admite `/versions/N` para repetir una práctica con la misma versión de datos.

El registro muestra la transferencia y la extracción; el tiempo y la barra animada indican que sigue trabajando. Al acabar verás cuántos archivos e imágenes hay. «Abrir carpeta descargada» permite verlos. Si contiene fotos compatibles, «Añadir imágenes al proyecto…» permite elegir la subcarpeta y su grupo. Revisa después las sesiones y los objetos relacionados; las etiquetas externas no se convierten automáticamente. Un conjunto de tablas CSV se puede descargar, pero no sirve directamente para entrenar este detector de imágenes.

Muchos datasets públicos se descargan sin token. Si Kaggle exige acceso, pulsa «Obtener token en Kaggle» y pégalo en el campo opcional. Se usa solo para esa descarga, no se guarda con el proyecto. Si hay condiciones que aceptar, debes hacerlo en la web del dataset. Al cancelar pueden quedar archivos parciales; revisa la carpeta o vuelve a intentarlo.

## Editar etiquetas y rectángulos

Arriba del editor, «Añadir etiqueta» crea una clase, «Renombrar» cambia su nombre en todas las fotografías y «Eliminar etiqueta» la elimina del proyecto. Si la etiqueta tiene rectángulos, se indica cuántos se borrarán y se pide confirmación. Las fotos se conservan y vuelven a quedar pendientes de revisión. Tras cambiar etiquetas debes entrenar de nuevo; el modelo anterior no se actualiza por sí solo.

Para cambiar únicamente la clase de un rectángulo, selecciónalo, elige la etiqueta correcta y pulsa «Cambiar etiqueta del rectángulo». «Borrar rectángulo» elimina solo el recuadro seleccionado. Los cambios de rectángulos se pueden deshacer durante la sesión; renombrar o eliminar etiquetas limpia ese historial.

## Mientras se entrena

Al pulsar «Entrenar y exportar», verás «Entrenando», el tiempo transcurrido y la tarea actual. La barra se anima durante la preparación; después muestra las épocas y el registro indica los lotes de imágenes procesados. La primera carga puede tardar porque prepara PyTorch y descarga los pesos si faltan. Puedes solicitar la cancelación; se completará la operación en curso antes de detenerse. Al final se indica «Completado», «Cancelado» o «Error».

## Probar con la cámara del PC

Después de entrenar o abrir un ZIP, ve a «3 · Prueba el detector» y pulsa «Probar cámara del PC…». Elige una cámara por su índice; «Buscar cámaras» comprueba los índices 0–9 disponibles. La cámara se activa al buscar o al pulsar «Iniciar cámara» y se libera al detener o cerrar la prueba. Si no abre, revisa los permisos de cámara para aplicaciones de escritorio de Windows y cierra otras aplicaciones que la estén usando.

Empieza con **640 × 480 y un límite de 5 FPS**. La ventana muestra la resolución que entrega realmente la cámara, los FPS procesados y los milisegundos de inferencia. Una resolución mayor puede hacer más lenta la captura; este modelo sigue procesando a 320 × 320. Cambia la confianza mínima mientras observas los resultados y compara los objetos encontrados con las falsas alarmas. «Vista en espejo» invierte la imagen y sus detecciones juntas.

Los recuadros muestran etiqueta y confianza. El contador corresponde a los objetos del fotograma actual. Puedes guardar una foto sin anotaciones o con las detecciones; «Detener» conserva la última imagen. Para cambiar de cámara, resolución o límite de FPS, detén la prueba y vuelve a iniciar con los ajustes nuevos.

## Las palabras que necesitas

| Concepto | Qué significa |
|---|---|
| Etiqueta o clase | Nombre de un tipo de objeto. |
| Rectángulo o caja | Ubicación de un objeto concreto. |
| Entrenamiento | Ajustar el modelo usando ejemplos anotados. |
| Época | Una vuelta sobre los ejemplos de entrenamiento. |
| Pérdida | Error que el entrenamiento intenta reducir. |
| Validación | Ejemplos usados para elegir la mejor época. |
| Prueba | Ejemplos reservados para evaluar al final. |
| Inferencia | Aplicar el modelo a una imagen nueva. |
| Despliegue | Preparar el modelo para ejecutarlo en la Pi. |

## Evaluar

Mantén juntas las fotos relacionadas. Repartir fotografías casi iguales entre entrenamiento y prueba puede producir un resultado engañosamente bueno.

La aplicación reutiliza un extractor visual aprendido y entrena las salidas de **etiqueta y ubicación**. La validación elige la época con mejor media AP50 y después se consulta la prueba reservada.

| Medida | Pregunta |
|---|---|
| Precisión | De los objetos predichos, ¿cuántos tienen etiqueta y ubicación correctas? |
| Recuperación | De los objetos presentes, ¿cuántos encuentra? |
| IoU | ¿Cuánto se solapan la caja real y la predicha? |
| AP50 | ¿Cómo se comporta al variar el umbral, exigiendo IoU de al menos 0,5? |

Una etiqueta equivocada cuenta como error aunque la caja esté bien situada. Revisa los resultados de cada etiqueta, además de la media. Una puntuación alta tampoco garantiza un acierto.

## Probar en la Raspberry Pi

Exporta el ZIP, abre la web de la Pi, introduce la clave y carga el modelo. Prueba imágenes nuevas y después la cámara. El cálculo se realiza en la Pi y el navegador muestra las cajas y sus etiquetas.

Registra qué objetos omite, qué falsas alarmas aparecen y qué etiquetas confunde. Cambia distancia, luz, posición y fondo. Guarda una nueva sesión para una prueba final independiente.

## Entrega de la práctica

- Explica qué etiquetas elegiste y por qué.
- Muestra una imagen con sus cajas y etiquetas.
- Justifica cómo has formado los grupos.
- Presenta las métricas de cada etiqueta y explica dos errores.
- Compara el mismo modelo y fotografía en Windows y en la Pi.

Para objetos diminutos puede hacer falta trabajar con recortes u otra resolución. El detector de esta práctica reduce las imágenes a 320 × 320; no puede recuperar detalles que desaparezcan al reducirlas.
