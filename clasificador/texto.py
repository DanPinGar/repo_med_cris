"""Normalización de textos para comparar nombres de medicamentos."""
import re
import unicodedata

# Palabras de sales, hidratos y ésteres que no cambian el principio activo.
SALES = {
    "sodica", "sodico", "potasica", "potasico", "magnesica", "magnesico", "calcica",
    "clorhidrato", "hidrocloruro", "hidrobromuro", "bromhidrato", "maleato", "besilato",
    "mesilato", "fumarato", "hemifumarato", "tartrato", "succinato", "trihidrato",
    "monohidrato", "dihidrato", "hemihidrato", "sesquihidrato", "anhidra", "anhidro",
    "hiclato", "bromuro", "dipropionato", "propionato", "furoato", "fosfato", "cilexetilo",
    "medoxomilo", "acetato", "valerato", "pivalato", "aceponato", "butirato", "base",
    "sal", "erbumina", "arginina", "tosilato", "dimesilato", "etexilato", "fumarato",
    "sacarosa", "nitrato", "clorhidratada", "micronizado", "micronizada",
}
VACIAS = {"de", "del", "la", "el", "y", "con", "en"}


def sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def norm(texto) -> str:
    """Minúsculas, sin acentos ni signos, espacios simples."""
    texto = sin_acentos(str(texto or "")).lower()
    texto = re.sub(r"[^a-z0-9+]+", " ", texto)
    return " ".join(texto.split())


def clave(texto) -> str:
    """Clave insensible al orden de palabras, a sales y a palabras vacías."""
    palabras = [p for p in norm(texto).replace("+", " ").split() if p not in VACIAS]
    sin_sales = [p for p in palabras if p not in SALES]
    return " ".join(sorted(sin_sales or palabras))


def capitalizar(texto: str) -> str:
    """Primera letra en mayúscula, el resto como venga."""
    texto = " ".join(str(texto or "").split())
    return texto[:1].upper() + texto[1:]


def componentes(texto: str) -> list[str]:
    """Separa 'a + b' o 'a/b' en sus partes."""
    partes = re.split(r"\s*\+\s*", texto)
    return [p.strip() for p in partes if p.strip()]
