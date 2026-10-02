"""Rellena MEDICAMENTOS.xlsx a partir de la columna Nombre.

Busca cada nombre en CIMA (AEMPS), obtiene sus principios activos y códigos ATC
y clasifica cada fármaco en los ensayos según reglas.xlsx.

    python rellenar.py           rellena solo las filas nuevas o incompletas
    python rellenar.py --todo    vuelve a calcular todas las filas
"""
import argparse
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from clasificador.catalogos import Catalogos
from clasificador.cima import Cima
from clasificador.excel import escribir, escribir_informe, leer
from clasificador.reglas import Reglas
from clasificador.resolver import Resolver, Resultado
from clasificador.texto import capitalizar, clave, norm

RAIZ = Path(__file__).resolve().parent
COLUMNAS_INICIALES = ["Nombre", "API/Comercial", "Principio activo (inglés)", "Descripción", "Área"]
COLUMNAS_FINALES = ["ATC", "Revisar"]


def comprobar_cerrado(ruta: Path) -> None:
    try:
        with open(ruta, "r+b"):
            pass
    except PermissionError:
        sys.exit(f"\n{ruta.name} está abierto en Excel. Ciérralo y vuelve a ejecutar.")


def dividir_nombres(filas: list[dict]) -> list[dict]:
    """'Atoraldo, Arrox' -> dos filas."""
    resultado = []
    for i, fila in enumerate(filas):
        partes = [p.strip() for p in fila["Nombre"].split(",")]
        if len(partes) > 1 and all(len(p) >= 3 for p in partes):
            for parte in partes:
                resultado.append({**fila, "Nombre": capitalizar(parte), "_origen": i, "_separada": True})
        else:
            resultado.append({**fila, "Nombre": capitalizar(fila["Nombre"]), "_origen": i})
    return resultado


def descripcion(res: Resultado, reglas: Reglas, cat: Catalogos) -> str:
    def texto(atc):
        if not atc:
            return ""
        return reglas.descripcion(atc) or capitalizar((cat.es.get(atc[:5]) or cat.es.get(atc, "")).lower())

    if len(res.componentes) <= 1 or reglas.no_descomponer(res.atc_producto):
        return texto(res.atc_producto)
    partes = [texto(c.atc) for c in res.componentes]
    if not all(partes):
        return texto(res.atc_producto)
    return " + ".join(dict.fromkeys(partes))


def construir(res: Resultado, reglas: Reglas, cat: Catalogos, resolver: Resolver) -> dict:
    if res.tipo == "marca":
        api = capitalizar(res.principio)
    else:
        api = ", ".join(res.marcas) or "Solo genéricos (EFG)"
    if reglas.no_descomponer(res.atc_producto):
        atcs = [res.atc_producto]
    else:
        atcs = [c.atc or res.atc_producto for c in res.componentes]
    fila = {
        "API/Comercial": api,
        "Principio activo (inglés)": resolver.ingles(res),
        "Descripción": descripcion(res, reglas, cat),
        "Área": reglas.area(res.atc_producto) or "Otros",
    }
    for ensayo in reglas.ensayos:
        fila[ensayo.columna] = reglas.clasificar(ensayo, atcs, res.vias)
    atcs_componentes = [c.atc for c in res.componentes]
    if len(atcs) > 1 and all(atcs_componentes):
        fila["ATC"] = f"{res.atc_producto} ({' + '.join(atcs_componentes)})"
    else:
        fila["ATC"] = res.atc_producto
    avisos = list(res.avisos)
    if not res.atc_producto:
        avisos.append("Sin código ATC")
    if "(?)" in fila["Principio activo (inglés)"]:
        avisos.append("Falta el nombre en inglés de algún componente (añadirlo en reglas.xlsx > Traducciones)")
    fila["Revisar"] = "; ".join(avisos)
    return fila


def resolver_todos(resolver: Resolver, nombres: list[str]) -> dict[str, Resultado]:
    resultados = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for i, (nombre, res) in enumerate(zip(nombres, pool.map(resolver.resolver, nombres)), start=1):
            resultados[nombre] = res
            if i % 20 == 0 or i == len(nombres):
                print(f"  {i}/{len(nombres)}")
    return resultados


def deduplicar(filas: list[dict]) -> tuple[list[dict], list[tuple]]:
    grupos = {}
    for fila in filas:
        grupos.setdefault(fila["_clave"], []).append(fila)
    finales, eliminadas = [], []
    for grupo in grupos.values():
        grupo.sort(key=lambda f: (norm(f["Nombre"]) != norm(f.get("_principio", "")),
                                  f["Nombre"].lower() != f.get("_principio", "").lower(),
                                  bool(f.get("Revisar")), f["_origen"]))
        finales.append(grupo[0])
        eliminadas += [(f, grupo[0]) for f in grupo[1:]]
    return finales, eliminadas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--todo", action="store_true", help="vuelve a calcular todas las filas")
    parser.add_argument("--excel", type=Path, default=RAIZ / "MEDICAMENTOS.xlsx")
    parser.add_argument("--reglas", type=Path, default=RAIZ / "reglas.xlsx")
    parser.add_argument("--actualizar", action="store_true", help="descarta la caché de CIMA y vuelve a consultar")
    args = parser.parse_args()

    comprobar_cerrado(args.excel)
    reglas = Reglas(args.reglas)
    cache = RAIZ / "datos" / "cache_cima"
    if args.actualizar and cache.exists():
        shutil.rmtree(cache)
    cima = Cima(cache)
    catalogos = Catalogos(cima, RAIZ / "datos" / "who_atc.csv")
    resolver = Resolver(cima, catalogos, reglas)
    columnas = COLUMNAS_INICIALES + [e.columna for e in reglas.ensayos] + COLUMNAS_FINALES
    generadas = [c for c in columnas if c not in ("Nombre", "Revisar")]

    originales = leer(args.excel)
    filas = dividir_nombres(originales)
    pendientes = [f for f in filas if args.todo or any(not f.get(c) for c in generadas)]
    nombres = list(dict.fromkeys(f["Nombre"] for f in pendientes))
    print(f"{len(filas)} filas; {len(pendientes)} por rellenar ({len(nombres)} nombres distintos).")
    print("Consultando CIMA...")
    resultados = resolver_todos(resolver, nombres)

    no_encontrados = []
    for fila in filas:
        fila["_clave"] = clave(fila["Nombre"])
        res = resultados.get(fila["Nombre"])
        if res is None:
            continue
        if res.tipo == "no encontrado":
            no_encontrados.append(fila["Nombre"])
            fila["Revisar"] = "; ".join(res.avisos) + " (se conservan los datos anteriores)"
            continue
        fila.update(construir(res, reglas, catalogos, resolver))
        if res.nombre_canonico:
            fila["Nombre"] = res.nombre_canonico
        if res.tipo == "principio":
            fila["_principio"] = res.principio
            fila["_clave"] = clave(res.principio)
        else:
            fila["_clave"] = clave(fila["Nombre"])

    for fila in filas:
        for columna, valor in reglas.correcciones.get(norm(fila["Nombre"]), {}).items():
            fila[columna] = valor

    filas, eliminadas = deduplicar(filas)
    filas.sort(key=lambda f: norm(f["Nombre"]))

    cambios = []
    for fila in filas:
        original = originales[fila["_origen"]]
        if fila.get("_separada"):
            cambios.append((fila["Nombre"], f"Separada de '{original['Nombre']}'", "", "", ""))
        elif fila["Nombre"] != original["Nombre"]:
            cambios.append((fila["Nombre"], "Nombre cambiado", "Nombre", original["Nombre"], fila["Nombre"]))
        for columna in columnas[1:]:
            antes, despues = original.get(columna, ""), fila.get(columna, "")
            if antes != despues:
                cambios.append((fila["Nombre"], "Valor cambiado", columna, antes, despues))
    for fila, superviviente in eliminadas:
        nombre = fila["Nombre"] if fila.get("_separada") else originales[fila["_origen"]]["Nombre"]
        cambios.append((nombre, f"Eliminada: duplicada de '{superviviente['Nombre']}'", "", "", ""))

    if not cambios:
        print("\nNo hay nada nuevo que rellenar; el Excel no se ha modificado.")
        return

    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    copias = args.excel.parent / "backups"
    copias.mkdir(exist_ok=True)
    copia = copias / f"{args.excel.stem}_{marca_tiempo}.xlsx"
    shutil.copy2(args.excel, copia)
    escribir(args.excel, filas, columnas)
    informes = args.excel.parent / "informes"
    informes.mkdir(exist_ok=True)
    informe = informes / f"cambios_{marca_tiempo}.xlsx"
    escribir_informe(informe, cambios)

    revisar = sum(1 for f in filas if f.get("Revisar"))
    print(f"\nListo: {len(filas)} filas guardadas en {args.excel.name}.")
    print(f"  Copia de seguridad: backups/{copia.name}")
    print(f"  Informe de cambios: informes/{informe.name} ({len(cambios)} cambios)")
    if eliminadas:
        print(f"  Duplicados eliminados: {len(eliminadas)}")
    print(f"  Filas para revisar (en amarillo): {revisar}")
    if no_encontrados:
        print("  No encontrados en CIMA: " + ", ".join(no_encontrados))
    print(f"  Consultas nuevas a CIMA: {cima.peticiones}")


if __name__ == "__main__":
    main()
