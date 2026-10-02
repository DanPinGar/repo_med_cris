# Clasificación de medicamentos

Rellena automáticamente `MEDICAMENTOS.xlsx` a partir de la columna **Nombre**:

| Columna | De dónde sale |
|---|---|
| API/Comercial |  Si el nombre es una marca → su principio activo. Si es un principio activo → sus dos marcas comercializadas más antiguas en España. |
| Principio activo (inglés) | Nombre oficial de la OMS (INN) según el código ATC. |
| Descripción / Área | Según el código ATC (hojas *Descripciones* y *Áreas* de `reglas.xlsx`). |
| Mylead, Paris, INOCA, COP, COMPLETE-2, ANGIODAPT | Categoría de cada ensayo según el código ATC (hoja *Categorías* de `reglas.xlsx`). |
| ATC | Código ATC usado para clasificar (en combinaciones, el de cada componente). |
| Revisar | Avisos: nombre no encontrado, interpretado de forma aproximada, etc. Las filas con aviso salen en amarillo. |

Los datos vienen de **CIMA** (Agencia Española de Medicamentos, `cima.aemps.es`) y de la tabla ATC de la **OMS**. No se usa inteligencia artificial: el mismo nombre da siempre el mismo resultado.

## Uso diario

1. Abre `MEDICAMENTOS.xlsx` y escribe los nombres nuevos en la columna **Nombre**, al final de la tabla. Se puede poner la marca (*Adiro*), el principio activo (*Bisoprolol*) o una combinación (*Ezetimiba + atorvastatina*).
2. Guarda y **cierra** el Excel.
3. Doble clic en **`rellenar.bat`**. Solo rellena las filas que tienen alguna columna vacía.
4. Abre el Excel y mira las filas en amarillo (columna *Revisar*).

Para volver a calcular **todas** las filas (por ejemplo, después de cambiar las reglas) usa **`regenerar_todo.bat`**.

Para corregir una fila a mano de forma permanente, no la edites en la tabla: añade la corrección en `reglas.xlsx` → hoja *Correcciones*. Si no, se perdería al regenerar.

## Reglas (`reglas.xlsx`)

| Hoja | Para qué sirve |
|---|---|
| Ensayos | Columnas del Excel y etiqueta para “cardiovascular sin categoría” (*others*) y “sin categoría” (`-`). |
| Categorías | Códigos ATC de cada categoría. Un fármaco entra si su ATC **empieza** por un código incluido y no por uno excluido. |
| Configuración | Qué ATC cuentan como cardiovasculares (por defecto `C` y `B01`). |
| Descripciones / Áreas | Texto según el ATC; gana el prefijo más largo. |
| Alias | Cómo buscar un nombre que CIMA no reconoce (p. ej. *Vitamina B6* → *piridoxina*). |
| ATC preferente | ATC forzado para principios activos con varios (el AAS como antiagregante). |
| Traducciones | Nombre en inglés cuando la OMS no lo da. |
| Correcciones | Valor fijo para una celda (Nombre + Columna). |

## Copias e informes

Cada ejecución guarda antes una copia en `backups/` y un listado de todo lo que ha cambiado en `informes/`.

## Instalación en otro ordenador

Hace falta Python 3.11 o superior (https://www.python.org/downloads/, marcando *Add python.exe to PATH*). La primera vez, `rellenar.bat` crea el entorno `.venv` e instala lo necesario (`requirements.txt`). Las consultas a CIMA se guardan en `datos/cache_cima`, así que las siguientes ejecuciones son rápidas. Con `rellenar.bat --actualizar` se descarta esa caché y se vuelve a consultar CIMA.
