"""Catálogos ATC: nombres en español (CIMA) y en inglés (OMS)."""
import csv
import difflib
import re
from pathlib import Path

from .cima import Cima
from .texto import clave

_COMBINACION_ES = re.compile(r"\by\b|combinac|,", re.I)
_COMBINACION_EN = re.compile(r"\band\b|combination|,", re.I)


class Catalogos:
    def __init__(self, cima: Cima, fichero_oms: Path):
        self.es = {a["codigo"]: a["nombre"] for a in cima.atc_completo()}
        self.en = {}
        with open(fichero_oms, encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                self.en.setdefault(fila["atc_code"], fila["atc_name"])
        self.indice_es = self._indice(self.es, _COMBINACION_ES)
        self.indice_en = self._indice(self.en, _COMBINACION_EN)

    @staticmethod
    def _indice(nombres: dict, combinacion: re.Pattern) -> dict[str, list[str]]:
        indice = {}
        for codigo, nombre in nombres.items():
            if len(codigo) == 7 and not combinacion.search(nombre):
                indice.setdefault(clave(nombre), []).append(codigo)
        return indice

    def codigos_es(self, nombre: str) -> list[str]:
        return self.indice_es.get(clave(nombre), [])

    def codigos_en(self, nombre: str) -> list[str]:
        return self.indice_en.get(clave(nombre), [])

    @staticmethod
    def _parecido(nombre: str, indice: dict, minimo: float) -> list[str]:
        cercanos = difflib.get_close_matches(clave(nombre), list(indice), n=1, cutoff=minimo)
        return indice[cercanos[0]] if cercanos else []

    def parecido_es(self, nombre: str, minimo=0.85) -> list[str]:
        return self._parecido(nombre, self.indice_es, minimo)

    def parecido_en(self, nombre: str, minimo=0.9) -> list[str]:
        return self._parecido(nombre, self.indice_en, minimo)

    def nombre_en(self, codigo: str) -> str:
        """Nombre OMS en inglés de un principio activo (vacío si es una combinación)."""
        nombre = self.en.get(codigo, "")
        return "" if _COMBINACION_EN.search(nombre) else nombre

    def combinacion_en(self, codigo: str) -> str:
        """Nombre OMS de una combinación concreta ('a and b' -> 'a + b'); vacío si es genérico."""
        nombre = self.en.get(codigo, "")
        if not nombre or re.search(r"combination|diuretic|excl|other|various|agents", nombre, re.I):
            return ""
        return re.sub(r",\s*|\s+and\s+", " + ", nombre)
