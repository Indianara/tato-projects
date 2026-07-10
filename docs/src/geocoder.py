"""
Módulo de geocodificação com cache local.

Pipeline:
  1. AwesomeAPI CEP (coordenadas diretas do CEP — cobre ~90%)
  2. ViaCEP + Nominatim (fallback comentado, será reativado)

Validações:
  - Coordenadas dentro do Brasil (bounding box)
  - Estado da coordenada coincide com o estado esperado do CSV
"""

import json
import re
import time
from pathlib import Path

import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

CACHE_FILE = Path(__file__).parent.parent / "cache" / "geocode_cache.json"
AWESOMEAPI_URL = "https://cep.awesomeapi.com.br/json/{cep}"
VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
NOMINATIM_USER_AGENT = "prestador-mais-proximo/1.0"
_GEOCODER = Nominatim(user_agent=NOMINATIM_USER_AGENT)

BRAZIL_BBOX = {"min_lat": -34, "max_lat": 5, "min_lng": -74, "max_lng": -34}
NOMINATIM_DELAY = 1.1
AWESOMEAPI_DELAY = 0.1

UF_MAP = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amapá": "AP",
    "amazonas": "AM", "bahia": "BA", "ceara": "CE", "ceará": "CE",
    "distrito federal": "DF", "espirito santo": "ES",
    "espírito santo": "ES", "goias": "GO", "goiás": "GO",
    "maranhao": "MA", "maranhão": "MA", "mato grosso": "MT",
    "mato grosso do sul": "MS", "minas gerais": "MG",
    "para": "PA", "pará": "PA", "paraiba": "PB", "paraíba": "PB",
    "parana": "PR", "paraná": "PR", "pernambuco": "PE",
    "piaui": "PI", "piauí": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS",
    "rondonia": "RO", "rondônia": "RO", "roraima": "RR",
    "santa catarina": "SC", "sao paulo": "SP", "são paulo": "SP",
    "sergipe": "SE", "tocantins": "TO",
}
UF_SET = set(UF_MAP.values())
SIGLA_UF_RE = re.compile(r"^[A-Z]{2}$")


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def normalize_cep(cep: str) -> str:
    return re.sub(r"\D", "", str(cep))


def _is_in_brazil(lat: float, lng: float) -> bool:
    return (
        BRAZIL_BBOX["min_lat"] <= lat <= BRAZIL_BBOX["max_lat"]
        and BRAZIL_BBOX["min_lng"] <= lng <= BRAZIL_BBOX["max_lng"]
    )


def _normalize_state_name(name: str) -> str:
    """Converte nome completo de estado para sigla (ex: 'Rio Grande do Sul' → 'RS')."""
    key = name.strip().lower()
    if SIGLA_UF_RE.match(key.upper()):
        return key.upper()
    return UF_MAP.get(key, "")


def _geocode_via_awesomeapi(cep: str, expected_state: str = "") -> dict | None:
    try:
        resp = requests.get(
            AWESOMEAPI_URL.format(cep=cep),
            timeout=10,
            headers={"User-Agent": NOMINATIM_USER_AGENT},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if "code" in data:
            return None
        lat = data.get("lat")
        lng = data.get("lng")
        state = data.get("state", "")
        if lat and lng:
            if expected_state and state and state.upper() != expected_state.upper():
                return None
            return {
                "lat": float(lat),
                "lng": float(lng),
                "city": data.get("city", ""),
                "state": state,
                "source": "awesomeapi",
            }
    except Exception:
        pass
    return None


def _geocode_via_viacep(cep: str) -> dict | None:
    try:
        resp = requests.get(VIACEP_URL.format(cep=cep), timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if "erro" in data:
            return None
        return {
            "logradouro": data.get("logradouro", ""),
            "bairro": data.get("bairro", ""),
            "cidade": data.get("localidade", ""),
            "uf": data.get("uf", ""),
            "source": "viacep",
        }
    except Exception:
        return None


def _geocode_via_nominatim(
    city: str = "",
    state: str = "",
    address: str = "",
    expected_state: str = "",
) -> dict | None:
    time.sleep(NOMINATIM_DELAY)

    queries = []
    if address:
        queries.append(address)
    if city and state:
        queries.append(f"{city}, {state}, Brazil")
    if city:
        queries.append(f"{city}, Brazil")

    for query in queries:
        try:
            loc = _GEOCODER.geocode(query, timeout=10)
            if not loc:
                continue
            if not _is_in_brazil(loc.latitude, loc.longitude):
                continue

            found_state = ""
            if loc.raw and "address" in loc.raw:
                raw_name = loc.raw["address"].get("state", "")
                found_state = _normalize_state_name(raw_name)

            if expected_state and found_state and found_state != expected_state:
                continue

            return {
                "lat": loc.latitude,
                "lng": loc.longitude,
                "city": city,
                "state": found_state or state,
                "source": "nominatim",
            }
        except GeocoderTimedOut:
            time.sleep(2)
        except Exception:
            pass
    return None


def _geocode_cep_single(
    cep_clean: str,
    cache: dict | None = None,
    expected_state: str = "",
) -> dict | None:
    """Tenta AwesomeAPI → fallback Nominatim comentado por enquanto."""
    if cache and cache.get(cep_clean):
        return cache[cep_clean]

    result = _geocode_via_awesomeapi(cep_clean, expected_state)
    time.sleep(AWESOMEAPI_DELAY)

    if result:
        if cache is not None:
            cache[cep_clean] = result
            _save_cache(cache)
        return result

    # -- Fallback ViaCEP + Nominatim comentado --
    # viacep = _geocode_via_viacep(cep_clean)
    # if viacep and viacep.get("logradouro"):
    #     full = (
    #         f"{viacep['logradouro']}, {viacep['bairro']}, "
    #         f"{viacep['cidade']}, {viacep['uf']}, Brazil"
    #     )
    #     viacep_uf = viacep.get("uf", "")
    #     if expected_state and viacep_uf and viacep_uf != expected_state:
    #         return None
    #     result = _geocode_via_nominatim(
    #         city=viacep["cidade"],
    #         state=viacep["uf"],
    #         address=full,
    #         expected_state=expected_state or viacep_uf,
    #     )

    return result


def geocode_cep(
    cep: str,
    city: str = "",
    state: str = "",
    cache: dict | None = None,
    auto_save: bool = True,
) -> dict | None:
    cep_clean = normalize_cep(cep)
    if len(cep_clean) != 8:
        return None
    if cache is None:
        cache = _load_cache()
    if cache.get(cep_clean):
        return cache[cep_clean]

    result = _geocode_cep_single(cep_clean, cache, expected_state=state)

    if result:
        cache[cep_clean] = result
        if auto_save:
            _save_cache(cache)
    return result


def batch_geocode(
    entries: list[dict],
    verbose: bool = True,
) -> dict:
    """
    Geocodifica lista de CEPs em lote.

    Etapas:
      1. Cache existente
      2. AwesomeAPI (rápida, coordenadas diretas)
      3. ViaCEP + Nominatim (fallback para CEPs não encontrados, 1 req/s)

    Cada entrada deve ter: 'cep' (obrigatório) e 'state' (opcional, para validação).
    """
    cache = _load_cache()
    results = {}

    unique_entries = {normalize_cep(e["cep"]): e for e in entries if e.get("cep")}

    already_cached = sum(1 for c in unique_entries if cache.get(c))
    to_fetch = {c: e for c, e in unique_entries.items() if not cache.get(c)}

    if verbose:
        print(
            f"  Cache: {already_cached} CEPs, "
            f"{len(to_fetch)} novos para processar."
        )

    if not to_fetch:
        for cep_clean in unique_entries:
            results[cep_clean] = cache.get(cep_clean)
        return results

    # ── Etapa 1: AwesomeAPI ──────────────────────────────────────────────
    if verbose:
        print(f"  [1/2] AwesomeAPI para {len(to_fetch)} CEPs...")

    try:
        from tqdm import tqdm
        it = tqdm(to_fetch.items(), desc="  AwesomeAPI", unit="cep")
    except ImportError:
        it = to_fetch.items()

    for cep_clean, entry in it:
        if cache.get(cep_clean):
            continue
        expected_state = (entry.get("state") or "").strip()
        result = _geocode_via_awesomeapi(cep_clean, expected_state)
        time.sleep(AWESOMEAPI_DELAY)
        if result:
            cache[cep_clean] = result
            _save_cache(cache)

    # ── Etapa 2: Nominatim fallback comentado ──────────────────────────
    # still_missing = {c: e for c, e in to_fetch.items() if not cache.get(c)}
    # if still_missing:
    #     if verbose:
    #         print(
    #             f"  [2/2] ViaCEP+Nominatim fallback para "
    #             f"{len(still_missing)} CEPs (1 req/s)..."
    #         )
    #     try:
    #         it = tqdm(still_missing.items(), desc="  Fallback", unit="cep")
    #     except ImportError:
    #         it = still_missing.items()
    #     for cep_clean, entry in it:
    #         if cache.get(cep_clean):
    #             continue
    #         expected_state = (entry.get("state") or "").strip()
    #         viacep = _geocode_via_viacep(cep_clean)
    #         time.sleep(0.05)
    #         if viacep and viacep.get("logradouro"):
    #             viacep_uf = viacep.get("uf", "")
    #             if expected_state and viacep_uf and viacep_uf != expected_state:
    #                 cache[cep_clean] = None
    #                 _save_cache(cache)
    #                 continue
    #             full = (
    #                 f"{viacep['logradouro']}, {viacep['bairro']}, "
    #                 f"{viacep['cidade']}, {viacep['uf']}, Brazil"
    #             )
    #             result = _geocode_via_nominatim(
    #                 city=viacep["cidade"],
    #                 state=viacep["uf"],
    #                 address=full,
    #                 expected_state=expected_state or viacep_uf,
    #             )
    #             if result:
    #                 cache[cep_clean] = result
    #                 _save_cache(cache)
    #             else:
    #                 cache[cep_clean] = None
    #                 _save_cache(cache)
    #         else:
    #             cache[cep_clean] = None
    #             _save_cache(cache)
    # else:
    #     if verbose:
    #         print("  Todos os CEPs resolvidos pela AwesomeAPI ✓")

    # Marcar CEPs sem resultado
    for cep_clean in to_fetch:
        if not cache.get(cep_clean):
            cache[cep_clean] = None
            _save_cache(cache)

    for cep_clean in unique_entries:
        results[cep_clean] = cache.get(cep_clean)

    if verbose:
        found = sum(1 for v in results.values() if v)
        awesome = sum(
            1 for v in results.values()
            if v and v.get("source") == "awesomeapi"
        )
        sem_coord = len(results) - found
        print(
            f"  Concluído: {found}/{len(results)} CEPs com coordenadas "
            f"({awesome} via AwesomeAPI)."
        )
        if sem_coord:
            print(f"  ⚠ {sem_coord} CEPs sem coordenada (sem fallback).")

    return results
