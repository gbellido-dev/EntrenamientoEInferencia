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

Una foto sin revisar no es lo mismo que una foto revisada sin objetos. Las fotos pendientes se omiten para no dar respuestas incorrectas al modelo.

Los ejemplos de la demostración son opcionales y pertenecen a otro proyecto. No necesitas incluir sus etiquetas ni sus imágenes en tu trabajo.

## Mientras se entrena

Al pulsar «Entrenar y exportar», verás «Entrenando», el tiempo transcurrido y la tarea actual. La barra se anima durante la preparación; después muestra las épocas y el registro indica los lotes de imágenes procesados. La primera carga puede tardar porque prepara PyTorch y descarga los pesos si faltan. Puedes solicitar la cancelación; se completará la operación en curso antes de detenerse. Al final se indica «Completado», «Cancelado» o «Error».

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
