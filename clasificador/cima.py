"""Cliente de la API pública de CIMA (AEMPS) con caché en disco."""
import hashlib
import json
import threading
import time
from pathlib import Path

import requests

BASE = "https://cima.aemps.es/cima/rest/"


class Cima:
    def __init__(self, carpeta_cache: Path):
        self.cache = Path(carpeta_cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._candados: dict[str, threading.Lock] = {}
        self._candado = threading.Lock()
        self.peticiones = 0

    def _sesion(self) -> requests.Session:
        if not hasattr(self._local, "sesion"):
            self._local.sesion = requests.Session()
            self._local.sesion.headers["User-Agent"] = "clasificacion-medicamentos/1.0"
        return self._local.sesion

    def _get(self, recurso: str, **params):
        clave = recurso + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        fichero = self.cache / (hashlib.sha1(clave.encode()).hexdigest() + ".json")
        with self._candado:
            candado = self._candados.setdefault(fichero.name, threading.Lock())
        with candado:
            return self._consultar(recurso, params, clave, fichero)

    def _consultar(self, recurso, params, clave, fichero):
        if fichero.exists():
            return json.loads(fichero.read_text("utf-8"))["datos"]
        for intento in range(5):
            try:
                r = self._sesion().get(BASE + recurso, params=params, timeout=90)
                r.raise_for_status()
                datos = r.json() if r.content else None
                break
            except (requests.RequestException, ValueError):
                if intento == 4:
                    raise
                time.sleep(3 * (intento + 1))
        self.peticiones += 1
        fichero.write_text(json.dumps({"consulta": clave, "datos": datos}, ensure_ascii=False), "utf-8")
        return datos

    def _paginado(self, recurso: str, **params) -> list[dict]:
        resultados, pagina = [], 1
        while True:
            datos = self._get(recurso, pagina=pagina, **params)
            lote = (datos or {}).get("resultados") or []
            resultados += lote
            if not lote or len(resultados) >= datos.get("totalFilas", 0):
                return resultados
            pagina += 1

    def buscar(self, **filtros) -> list[dict]:
        """Busca presentaciones (nombre=, practiv1=, practiv2=, atc=)."""
        return self._paginado("medicamentos", **filtros)

    def total(self, **filtros) -> int:
        return ((self._get("medicamentos", pagina=1, **filtros)) or {}).get("totalFilas", 0)

    def medicamento(self, nregistro) -> dict:
        return self._get("medicamento", nregistro=nregistro) or {}

    def atc_completo(self) -> list[dict]:
        """Todos los códigos ATC con su nombre en español.

        La API solo devuelve la lista entera si recibe algún filtro, aunque no lo aplique.
        """
        return self._paginado("maestras", maestra=7, codigo="A")
