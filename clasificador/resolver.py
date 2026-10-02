"""Convierte un nombre escrito (marca, principio activo, combinación o nombre en inglés)
en principios activos con su código ATC, consultando CIMA."""
import difflib
import re
from collections import Counter
from dataclasses import dataclass, field

from .catalogos import Catalogos
from .cima import Cima
from .reglas import Reglas
from .texto import capitalizar, clave, componentes, norm, sin_acentos

# Palabras que marcan el final del nombre comercial dentro del nombre de una presentación.
FORMAS = {
    "comprimido", "comprimidos", "capsula", "capsulas", "solucion", "suspension", "polvo",
    "granulado", "sobre", "sobres", "crema", "pomada", "gel", "colirio", "gotas", "jarabe",
    "inyectable", "parche", "parches", "emulsion", "locion", "champu", "supositorios",
    "ovulos", "aerosol", "inhalador", "pluma", "plumas", "vial", "jeringa", "jeringas",
    "concentrado", "liofilizado", "espuma", "pasta", "polvos", "efg", "pastillas", "chicles",
    "microgranulos", "unguento", "spray", "dispositivo", "implante", "colutorio",
}


@dataclass
class Componente:
    nombre: str
    atc: str = ""
    ingles: str = ""


@dataclass
class Resultado:
    escrito: str
    tipo: str  # "marca", "principio" o "no encontrado"
    principio: str = ""
    componentes: list[Componente] = field(default_factory=list)
    atc_producto: str = ""
    vias: list[str] = field(default_factory=list)
    marcas: list[str] = field(default_factory=list)
    nombre_canonico: str = ""  # se usa como Nombre si el escrito venía en inglés
    avisos: list[str] = field(default_factory=list)


def marca_de(nombre_presentacion: str) -> str:
    palabras = []
    for palabra in nombre_presentacion.split():
        if palabra[:1].isdigit() or norm(palabra) in FORMAS:
            break
        palabras.append(palabra)
    return " ".join(palabras).strip(" ,.-/")


def compacto(texto: str) -> str:
    return norm(texto).replace(" ", "")


def vtm_de(presentacion: dict) -> str:
    return " ".join(((presentacion.get("vtm") or {}).get("nombre") or "").split())


def partes_vtm(vtm: str) -> list[str]:
    return [p.strip() for p in vtm.split("+") if p.strip()]


def es_simple(vtm: str) -> bool:
    return bool(vtm) and "+" not in vtm and norm(vtm) != "multicomponente"


def numero_registro(presentacion: dict) -> int:
    digitos = re.sub(r"\D", "", str(presentacion.get("nregistro", "")))
    return int(digitos) if digitos else 10**12


def prefijo_comun(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def titulo(marca: str) -> str:
    return " ".join(p if p in {"AAS"} else p.capitalize() for p in marca.split())


def variantes(texto: str) -> tuple[str, str, str]:
    """(texto completo, contenido del paréntesis, texto sin paréntesis)."""
    dentro = " ".join(re.findall(r"\(([^)]*)\)", texto))
    fuera = re.sub(r"\([^)]*\)", " ", texto)
    return " ".join(texto.split()), " ".join(dentro.split()), " ".join(fuera.split())


def mismo_principio(a: str, b: str) -> bool:
    ca, cb = clave(a), clave(b)
    return ca == cb or difflib.SequenceMatcher(None, ca, cb).ratio() >= 0.85


class Resolver:
    def __init__(self, cima: Cima, catalogos: Catalogos, reglas: Reglas):
        self.cima = cima
        self.cat = catalogos
        self.reglas = reglas

    # ---------- consultas a CIMA ----------

    def _buscar_principio(self, nombre: str) -> list[dict]:
        """Presentaciones que contienen el principio activo.

        CIMA solo encuentra el nombre tal como lo guarda ('IPRATROPIO BROMURO'), así que si
        la búsqueda literal no da con él se prueba con su palabra más larga ('ipratropio').
        """
        objetivo = clave(nombre)
        palabras = objetivo.split() or [norm(nombre)]
        resultados = []
        for consulta in dict.fromkeys([sin_acentos(nombre).strip(), max(palabras, key=len)]):
            if len(consulta) < 3:
                continue
            resultados = self.cima.buscar(practiv1=consulta)
            if any(objetivo in {clave(x) for x in partes_vtm(vtm_de(p))} for p in resultados):
                return resultados
        return resultados

    def _atc_presentacion(self, presentacion: dict) -> str:
        atcs = self.cima.medicamento(presentacion["nregistro"]).get("atcs") or []
        atcs = sorted(atcs, key=lambda a: a.get("nivel", 0), reverse=True)
        return atcs[0]["codigo"] if atcs else ""

    def _atcs_muestra(self, presentaciones: list[dict]) -> Counter:
        """Códigos ATC del principio activo, ponderados por número de presentaciones.

        Se consulta una presentación por cada combinación de vía, forma y dosis.
        """
        comercializadas = [p for p in presentaciones if p.get("comerc")] or presentaciones
        grupos = {}
        for p in sorted(comercializadas, key=numero_registro):
            vias = tuple(v.get("nombre", "") for v in p.get("viasAdministracion") or [])
            forma = (p.get("formaFarmaceutica") or {}).get("nombre", "")
            grupos.setdefault((vias, forma, p.get("dosis", "")), []).append(p)
        cuenta = Counter()
        for grupo in sorted(grupos.values(), key=len, reverse=True)[:8]:
            atc = self._atc_presentacion(grupo[0])
            if atc:
                cuenta[atc] += len(grupo)
        return cuenta

    def _elegir_atc(self, principio: str, cuenta: Counter, contexto: str = "") -> str:
        preferente = self.reglas.atc_preferente.get(clave(principio))
        if preferente:
            return preferente
        if contexto:
            candidatos = set(cuenta) | set(self.cat.codigos_es(principio))
            if not candidatos:
                return ""
            return max(sorted(candidatos), key=lambda c: (prefijo_comun(c, contexto), self.reglas.es_cv(c), cuenta[c]))
        if not cuenta:
            codigos = self.cat.codigos_es(principio)
            return codigos[0] if codigos else ""
        return max(sorted(cuenta), key=lambda c: cuenta[c])

    def _ingles(self, principio: str, atc: str) -> str:
        traduccion = self.reglas.traducciones.get(clave(principio))
        if traduccion:
            return traduccion
        if atc and self.cat.nombre_en(atc):
            return self.cat.nombre_en(atc)
        for codigo in self.cat.codigos_es(principio):
            if self.cat.nombre_en(codigo):
                return self.cat.nombre_en(codigo)
        return ""

    def _marcas(self, presentaciones: list[dict], principios: list[str]) -> list[str]:
        """Las dos marcas comercializadas más antiguas (sin genéricos)."""
        prohibidas = {w for p in principios for w in norm(p).split() if len(w) > 3}
        prohibidas |= {norm(p).split()[0] for p in principios if norm(p)}
        grupos = {}
        for p in presentaciones:
            if p.get("generico"):
                continue
            marca = marca_de(p.get("nombre", ""))
            palabras = norm(marca).split()
            if not palabras or prohibidas & set(palabras):
                continue
            g = grupos.setdefault(palabras[0], {"variantes": set(), "comerc": False, "registro": 10**13})
            g["variantes"].add(titulo(marca))
            g["comerc"] |= bool(p.get("comerc"))
            g["registro"] = min(g["registro"], numero_registro(p))
        orden = sorted(grupos.values(), key=lambda g: (not g["comerc"], g["registro"]))
        return [min(g["variantes"], key=lambda v: (len(v.split()), v)) for g in orden[:2]]

    # ---------- principios activos ----------

    def _simples(self, principio: str) -> list[dict]:
        return [p for p in self._buscar_principio(principio)
                if es_simple(vtm_de(p)) and clave(vtm_de(p)) == clave(principio)]

    def componente(self, principio: str, contexto: str = "") -> Componente:
        cuenta = self._atcs_muestra(self._simples(principio))
        atc = self._elegir_atc(principio, cuenta, contexto)
        return Componente(principio, atc, self._ingles(principio, atc))

    def _principio_exacto(self, texto: str) -> str:
        """Nombre del principio activo en CIMA si 'texto' lo es exactamente."""
        if len(norm(texto)) < 3:
            return ""
        nombres = Counter(vtm_de(p) for p in self._buscar_principio(texto)
                          if es_simple(vtm_de(p)) and clave(vtm_de(p)) == clave(texto))
        if nombres:
            return nombres.most_common(1)[0][0]
        return self._principio_por_atc(self.cat.codigos_es(texto))

    def _principio_por_atc(self, codigos: list[str]) -> str:
        for codigo in codigos:
            nombres = Counter(vtm_de(p) for p in self.cima.buscar(atc=codigo) if es_simple(vtm_de(p)))
            if nombres:
                return nombres.most_common(1)[0][0]
        return ""

    def _principio_aproximado(self, texto: str) -> str:
        palabras = sorted((w for w in norm(texto).split() if len(w) >= 5), key=len, reverse=True)
        if palabras:
            candidatos = {vtm_de(p) for p in self.cima.buscar(practiv1=palabras[0]) if es_simple(vtm_de(p))}
            parecidos = difflib.get_close_matches(clave(texto), [clave(c) for c in candidatos], n=1, cutoff=0.85)
            if parecidos:
                return next(c for c in candidatos if clave(c) == parecidos[0])
        return self._principio_por_atc(self.cat.parecido_es(texto))

    def _resultado_principio(self, escrito: str, principio: str) -> Resultado:
        simples = self._simples(principio)
        comp = self.componente(principio)
        res = Resultado(escrito, "principio", principio, [comp], comp.atc)
        res.marcas = self._marcas(simples, [principio])
        if not simples:
            res.avisos.append("No hay medicamentos en CIMA con solo este principio activo")
        return res

    def _como_principio(self, escrito: str, texto: str) -> Resultado | None:
        principio = self._principio_exacto(texto)
        return self._resultado_principio(escrito, principio) if principio else None

    # ---------- marcas ----------

    def _presentaciones_marca(self, texto: str) -> tuple[list[dict], list[dict]]:
        """(presentaciones con esa marca exacta, presentaciones de variantes: 'Humalog KwikPen')."""
        objetivo = norm(texto)
        presentaciones = [p for p in self.cima.buscar(nombre=texto) if vtm_de(p)]
        exactas = [p for p in presentaciones if norm(marca_de(p["nombre"])) == objetivo]
        variantes_ = [p for p in presentaciones if norm(marca_de(p["nombre"])).startswith(objetivo + " ")]
        if not exactas and not variantes_ and len(objetivo) >= 6:
            # 'Ferogradumet' frente a 'FERO-GRADUMET': se compara sin espacios ni guiones.
            junto = compacto(texto)
            exactas = [p for p in self.cima.buscar(nombre=objetivo[:4])
                       if vtm_de(p) and compacto(marca_de(p["nombre"])) == junto]
        return exactas, variantes_

    def _como_marca(self, escrito: str, texto: str) -> Resultado | None:
        if len(norm(texto)) < 3:
            return None
        exactas, variantes_ = self._presentaciones_marca(texto)
        elegidas = exactas + variantes_
        if not elegidas:
            return None
        # La composición la decide la marca exacta; el representante, mejor si está comercializado.
        vtm = Counter(vtm_de(p) for p in (exactas or variantes_)).most_common(1)[0][0]
        candidatas = [p for p in elegidas if vtm_de(p) == vtm]
        base = [p for p in candidatas if p.get("comerc")] or candidatas
        representante = min(base, key=lambda p: (p not in exactas, numero_registro(p)))
        atc = self._atc_presentacion(representante)
        vias = [v.get("nombre", "") for v in representante.get("viasAdministracion") or []]
        res = Resultado(escrito, "marca", vtm, atc_producto=atc, vias=vias)
        partes = partes_vtm(vtm)
        if len(partes) == 1:
            res.componentes = [Componente(vtm, atc, self._ingles(vtm, atc))]
        else:
            res.componentes = [self.componente(p, atc) for p in partes]
        if not any(p.get("comerc") for p in candidatas):
            res.avisos.append("Marca no comercializada actualmente")
        return res

    # ---------- combinaciones escritas como 'a + b' ----------

    def _presentaciones_combinacion(self, partes: list[str]) -> list[dict]:
        """Presentaciones cuyos principios activos son exactamente 'partes'."""
        for parte in partes:
            encontradas = []
            for p in self._buscar_principio(parte):
                piezas = partes_vtm(vtm_de(p))
                if len(piezas) == len(partes) and all(any(mismo_principio(x, y) for y in piezas) for x in partes):
                    encontradas.append(p)
            if encontradas:
                return encontradas
        return []

    def _combinacion(self, escrito: str, partes: list[str]) -> Resultado:
        presentaciones = self._presentaciones_combinacion(partes)
        if presentaciones:
            base = [p for p in presentaciones if p.get("comerc")] or presentaciones
            representante = min(base, key=numero_registro)
            principios = partes_vtm(vtm_de(representante))
            res = Resultado(escrito, "principio", " + ".join(principios))
            res.atc_producto = self._atc_presentacion(representante)
            res.marcas = self._marcas(presentaciones, principios)
        else:
            principios = []
            for parte in partes:
                principio = (self._principio_exacto(parte) or self._principio_por_atc(self.cat.codigos_en(parte))
                             or self._principio_aproximado(parte))
                if not principio:
                    return Resultado(escrito, "no encontrado", avisos=[f"No se encontró el principio activo '{parte}'"])
                principios.append(principio)
            res = Resultado(escrito, "principio", " + ".join(principios))
            res.avisos.append("No hay ningún medicamento en CIMA con esta combinación")
        res.componentes = [self.componente(p, res.atc_producto) for p in principios]
        if not res.atc_producto and res.componentes:
            res.atc_producto = res.componentes[0].atc
        return res

    # ---------- entrada principal ----------

    def resolver(self, escrito: str) -> Resultado:
        alias = self.reglas.alias.get(norm(escrito))
        if alias:
            res = self._resolver(escrito, alias)
            if res.tipo == "principio":
                # Marca extranjera o retirada: en API/Comercial va su principio activo.
                res.tipo, res.marcas = "marca", []
            return res
        return self._resolver(escrito, escrito)

    def _resolver(self, escrito: str, texto: str) -> Resultado:
        if len(componentes(texto)) > 1:
            return self._combinacion(escrito, componentes(texto))
        completo, dentro, fuera = variantes(texto)
        orden_principio = list(dict.fromkeys(v for v in (completo, dentro, fuera) if v))
        orden_marca = list(dict.fromkeys(v for v in (completo, fuera, dentro) if v))

        for v in orden_principio:
            res = self._como_principio(escrito, v)
            if res:
                return res
        for v in orden_marca:
            res = self._como_marca(escrito, v)
            if res:
                return res
        for v in orden_principio:
            en_ingles = self.cat.codigos_en(v)
            principio = self._principio_por_atc(en_ingles)
            if principio:
                return self._renombrado(escrito, principio, "Escrito en inglés")
        for v in orden_principio:
            principio = self._principio_aproximado(v) or self._principio_por_atc(self.cat.parecido_en(v))
            if principio:
                return self._renombrado(escrito, principio, "Nombre aproximado")
        return Resultado(escrito, "no encontrado", avisos=["No encontrado en CIMA"])

    def _renombrado(self, escrito: str, principio: str, motivo: str) -> Resultado:
        res = self._resultado_principio(escrito, principio)
        res.nombre_canonico = capitalizar(principio)
        res.avisos.append(f"{motivo}: '{escrito}' se ha cambiado a '{res.nombre_canonico}'")
        return res

    # ---------- textos de salida ----------

    def ingles(self, res: Resultado) -> str:
        nombres = [c.ingles for c in res.componentes]
        if nombres and all(nombres):
            return " + ".join(dict.fromkeys(nombres))
        combinado = self.cat.combinacion_en(res.atc_producto)
        if combinado:
            return combinado
        return " + ".join(n or f"{c.nombre} (?)" for n, c in zip(nombres, res.componentes))
