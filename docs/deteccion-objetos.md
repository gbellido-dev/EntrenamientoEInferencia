# Aprender a detectar objetos con rectángulos y etiquetas

## Sí: este es el funcionamiento

Una imagen puede contener varios objetos. Para cada uno guardamos **dónde está** (su rectángulo) y **qué es** (su clase). Por ejemplo:

| Imagen | Rectángulo | Etiqueta |
|---|---|---|
| patio.jpg | El que rodea la pelota de la izquierda | Pelota |
| patio.jpg | El que rodea otra pelota | Pelota |
| patio.jpg | El que rodea una cara | Cara |

Después entrenamos con muchas imágenes anotadas. Ante una foto nueva, el modelo intenta devolver los rectángulos, las clases aprendidas y sus puntuaciones. Puede devolver cero, uno o varios objetos.

**Imagen → marcar rectángulos y etiquetas → revisar → entrenar → evaluar → exportar → usar con fotos nuevas o cámara.**

Puedes preparar un proyecto solo para caras, otro para pelotas, otro para tipos de células o uno con varias clases. El modelo aprende las clases de su proyecto; no pasa a reconocer automáticamente cualquier cosa. Las fotos que use después deben ser comparables con las de entrenamiento.

## Cómo usar la aplicación

Abre **`iniciar_objetos.cmd`**. Es la única versión de la aplicación.

1. **Nuevo proyecto:** elige dónde guardarlo. Empieza vacío, sin etiquetas predefinidas.
2. **Añadir etiqueta:** escribe únicamente la etiqueta que necesites. Puedes trabajar con una sola o añadir más después.
2. **Añadir fotos:** selecciona una carpeta y asigna el grupo de captura. No se modifican los originales.
3. **Elegir clase:** en «Clase del rectángulo», selecciona qué objeto vas a marcar.
4. **Dibujar:** arrastra un rectángulo ajustado alrededor del objeto. Repite con todos los objetos de las clases del proyecto.
5. **Corregir:** clic para seleccionar un rectángulo; elige otra clase y pulsa «Aplicar al seleccionado». Supr borra la caja. Para cambiar su tamaño, bórrala y dibuja otra. «Deshacer rectángulos» recupera el estado anterior durante la sesión.
6. **Revisar:** confirma la revisión. Para una imagen sin ninguno de los objetos de tus clases, usa «Confirmar sin objetos». No dibujes cajas de fondo.
7. **Entrenar y evaluar:** revisa los grupos y ajusta épocas y tasa. El proceso se ejecuta en segundo plano y permite cancelar.
8. **Exportar:** copia `detector-objetos.zip` y cárgalo en la web de la Pi.

Cada rectángulo tiene su propia etiqueta; cambiar el selector solo afecta a las cajas nuevas. Para modificar una existente debes seleccionarla y aplicar la etiqueta. «Añadir etiqueta» amplía el proyecto y requiere entrenar un modelo nuevo para aprenderla.

Para fotos con un solo objeto, activa **«Pasar a la siguiente imagen al dibujar un rectángulo»**. Se guarda la anotación y se avanza al terminar de dibujar. La casilla empieza desactivada para permitir varias cajas en una misma foto. Cambiar etiquetas, seleccionar o borrar cajas no provoca el avance; tampoco se avanza si falla el guardado.

Las fotografías nuevas quedan pendientes hasta anotarlas o confirmar su revisión. Una imagen pendiente y vacía no equivale a una imagen negativa revisada. Las cajas, sus etiquetas y los descartes se guardan automáticamente.

## Ejemplo preparado

En este equipo puedes abrir `demo-data/objetos/proyecto.json`: muestra escenas dibujadas con **Pelota** y **Caja**, ambas en cada imagen. Es material artificial para practicar la herramienta, no una evaluación de objetos reales.

Para generarlo de nuevo:

```powershell
.\.venv\Scripts\python.exe -m scripts.crear_demo_objetos
```

El dataset descargado de Kaggle es material opcional; puedes importar su `annotations.xml`. El lector CVAT conserva las etiquetas de sus rectángulos. Las cajas giradas se convierten en rectángulos horizontales envolventes.

## Preparar buenos datos

Marca **todos los objetos de las clases elegidas** en cada foto, no solo el más grande. Si dejas alguno sin marcar, el entrenamiento podría tratarlo como fondo.

Recoge variedad de tamaños, posiciones, luz y fondos. Incluye imágenes con varios objetos e imágenes sin objetos de esas clases. Mantén juntas las fotos relacionadas de una sesión, un mismo objeto, persona o muestra microscópica mediante el mismo grupo.

El reparto intenta 60/20/20 conservando grupos completos y todas las clases en cada conjunto. Exige al menos seis imágenes revisadas y tres grupos; cada clase necesita ejemplos en tres grupos. Son requisitos mínimos de funcionamiento, no una garantía de datos suficientes. Más variedad independiente suele ser más valiosa que muchas fotos casi iguales.

Los grupos iniciales del importador CVAT se basan en la imagen. No demuestran que las personas, objetos o muestras sean independientes: debes revisarlos. Reserva una nueva sesión para la evaluación externa.

## Qué se entrena y qué se mide

Se usa SSDLite MobileNetV3 con pesos oficiales de torchvision. El extractor visual se mantiene congelado y se entrenan las cabezas que predicen **clase y coordenadas**. Para C clases del proyecto hay también una clase interna de fondo. Se añade señal de aprendizaje de fondo para las imágenes negativas revisadas (pérdida sobre los 32 candidatos de fondo más difíciles de cada imagen negativa).

Las imágenes se preparan a 320 × 320 para reducir el coste en la Pi 4. Los rectángulos se ajustan a esa escala y la salida se devuelve en coordenadas de la foto original. Se mantienen los píxeles originales, sin reinterpretar EXIF, para coincidir con las anotaciones. Hay una caché acotada de imágenes reducidas para el entrenamiento en Windows; no se entrena en la Pi.

| Medida | Explicación |
|---|---|
| Pérdida | Error que intenta reducir el entrenamiento. |
| Precisión | De los objetos marcados por el modelo, cuántos tienen clase y ubicación correctas. |
| Recuperación | De los objetos anotados, cuántos encuentra. |
| IoU | Solapamiento entre la caja real y la predicha. |
| AP50 por clase | Resumen de precisión/recuperación al variar el umbral, exigiendo clase correcta e IoU ≥ 0,5. |
| Media AP50 | Promedio de AP50 entre las clases, dando el mismo peso a cada clase. |

Se selecciona la mejor época por la media AP50 de validación y luego se consulta la prueba reservada. Las cifras de precisión y recuperación se calculan a umbral 0,5. AP50 usa candidatos desde 0,01; no es el mAP COCO de varios umbrales de IoU. Confundir una pelota con una célula cuenta como error aunque el rectángulo sea correcto.

La supresión de rectángulos duplicados se aplica **por clase**. Un mismo rectángulo puede generar más de una hipótesis si dos clases superan el umbral: revisa las puntuaciones y el entrenamiento. No se fusionan silenciosamente clases diferentes.

## Exportación y cámara

El ZIP contiene el ONNX, el manifiesto con las etiquetas en orden y las métricas. Se usa `task=object_detection`, entrada float32 `[1,3,320,320]`, cajas `[1,N,4]` y puntuaciones `[1,N,C]`. Se verifica la equivalencia numérica ONNX/PyTorch antes de publicar el paquete.

En la web carga el ZIP, introduce la clave y pulsa «Iniciar cámara». Verás **rectángulo, etiqueta y puntuación**. La cámara usada está conectada al servidor, normalmente la Raspberry Pi, y la inferencia ocurre allí. La web también permite subir una foto de prueba.

La configuración USB/CSI y el servicio están en [la guía de la Raspberry Pi](raspberry-pi.md). La captura del hardware y la velocidad todavía deben comprobarse en la Pi real.

Por terminal:

```powershell
.\.venv\Scripts\python.exe -m scripts.entrenar_objetos projects/mi-proyecto/proyecto.json --epochs 15
```

## Prácticas para alumnos

1. Anota una imagen con varios objetos de dos clases. Explica qué información guarda cada caja.
2. Cambia una etiqueta incorrecta y comprueba que las otras cajas no cambian.
3. Compara una imagen pendiente con una imagen confirmada sin objetos.
4. Entrena y revisa las métricas de cada clase; una media alta puede ocultar una clase peor.
5. Prueba imágenes de otra sesión y luego la cámara. Registra omisiones, falsas alarmas y confusiones.
6. Cambia el umbral: ¿qué mejora y qué empeora?

Para **células u objetos diminutos**, reducir una imagen grande a 320 × 320 puede eliminar el detalle necesario. Puede hacer falta trabajar con recortes, otra resolución o un modelo especializado. Para separar el contorno exacto de cada célula se necesitaría segmentación, una tarea distinta de los rectángulos. La herramienta genérica proporciona el recorrido; el rendimiento depende de los datos y del problema.
