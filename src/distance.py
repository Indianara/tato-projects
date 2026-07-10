"""
Módulo de cálculo de distâncias.

Etapa 1 — Haversine: distância em linha reta (rápido, sem API).
Etapa 2 — OSRM: distância real por estradas (API pública gratuita).
           Usado apenas para os top N candidatos do Haversine, minimizando chamadas.
"""

import math
import time
import requests

OSRM_TABLE_URL = "http://router.project-osrm.org/table/v1/driving/{coords}"
OSRM_ROUTE_URL = "http://router.project-osrm.org/route/v1/driving/{coords}"
OSRM_TIMEOUT = 15
EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calcula distância em km entre dois pontos geográficos (linha reta).
    """
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def top_n_haversine(
    origin_lat: float,
    origin_lng: float,
    candidates: list[dict],
    n: int = 15,
) -> list[dict]:
    """
    Retorna os N candidatos mais próximos por distância Haversine.

    Args:
        origin_lat/origin_lng: Coordenadas do carro
        candidates: Lista de dicts com chaves 'lat', 'lng' e demais dados do prestador
        n: Quantos candidatos retornar

    Returns:
        Lista de até N dicts com chave extra 'haversine_km'
    """
    scored = []
    for c in candidates:
        if c.get("lat") is None or c.get("lng") is None:
            continue
        dist = haversine_km(origin_lat, origin_lng, c["lat"], c["lng"])
        scored.append({**c, "haversine_km": round(dist, 2)})

    scored.sort(key=lambda x: x["haversine_km"])
    return scored[:n]


def osrm_route_distance(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> float | None:
    """Consulta rota individual no OSRM quando o table endpoint retorna zero/inválido."""
    coords_str = f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
    url = OSRM_ROUTE_URL.format(coords=coords_str)

    try:
        resp = requests.get(
            url,
            params={
                "overview": "false",
                "alternatives": "false",
                "steps": "false",
            },
            timeout=OSRM_TIMEOUT,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        routes = data.get("routes") or []
        if not routes:
            return None

        meters = routes[0].get("distance")
        if meters is None or meters <= 0:
            return None

        return round(meters / 1000, 2)
    except Exception:
        return None


def sanitize_distance_km(
    road_km: float | None,
    route_fallback: float | None,
    haversine_fallback: float | None,
) -> float | None:
    """
    Normaliza a distância final priorizando a rota real.

    Regras:
    - usa OSRM table quando válido
    - usa OSRM route quando table retorna 0/inválido
    - usa Haversine apenas como último fallback
    """
    candidate = road_km

    if candidate is None or candidate <= 0:
        candidate = route_fallback

    if candidate is None or candidate <= 0:
        candidate = haversine_fallback

    if candidate is None:
        return None

    return round(candidate, 2)


def osrm_road_distances(
    origin_lat: float,
    origin_lng: float,
    destinations: list[dict],
    delay_seconds: float = 0.5,
) -> list[dict]:
    """
    Consulta OSRM table endpoint para obter distâncias reais por estrada.
    Envia 1 origem + N destinos em uma única chamada.

    Args:
        origin_lat/origin_lng: Coordenadas do carro (source)
        destinations: Lista de dicts com 'lat', 'lng' e dados do prestador
        delay_seconds: Delay antes da chamada (rate limiting)

    Returns:
        Lista de dicts com chave 'road_km' adicionada.
        Em caso de falha, usa 'haversine_km' como fallback.
    """
    if not destinations:
        return []

    time.sleep(delay_seconds)

    # Formato OSRM: lng,lat (longitude primeiro)
    coords_str = f"{origin_lng},{origin_lat}"
    for d in destinations:
        coords_str += f";{d['lng']},{d['lat']}"

    # sources=0 significa que o índice 0 (origem) é a fonte
    # destinations=1;2;3... são os destinos
    dest_indices = ";".join(str(i + 1) for i in range(len(destinations)))
    url = OSRM_TABLE_URL.format(coords=coords_str)

    try:
        resp = requests.get(
            url,
            params={
                "sources": "0",
                "destinations": dest_indices,
                "annotations": "distance",
            },
            timeout=OSRM_TIMEOUT,
        )

        if resp.status_code == 200:
            data = resp.json()
            # distances[0] é a linha da origem (índice 0) para cada destino
            distances = data.get("distances", [[]])[0]

            results = []
            for i, dest in enumerate(destinations):
                meters = distances[i] if i < len(distances) else None
                if meters is not None and meters >= 0:
                    road_km = meters / 1000
                else:
                    road_km = None

                route_fallback = None
                if road_km is None or road_km <= 0:
                    route_fallback = osrm_route_distance(
                        origin_lat,
                        origin_lng,
                        dest["lat"],
                        dest["lng"],
                    )

                results.append(
                    {
                        **dest,
                        "road_km": sanitize_distance_km(
                            road_km,
                            route_fallback,
                            dest.get("haversine_km"),
                        ),
                    }
                )
            return results

    except Exception:
        pass

    # Fallback completo: usar Haversine para todos
    return [
        {
            **d,
            "road_km": sanitize_distance_km(None, None, d.get("haversine_km")),
        }
        for d in destinations
    ]


def find_nearest(
    origin_lat: float,
    origin_lng: float,
    candidates: list[dict],
    top_n: int = 3,
    pre_filter: int = 15,
    osrm_delay: float = 0.5,
) -> list[dict]:
    """
    Pipeline completo: Haversine pré-filtro → OSRM road distance → top N.

    Args:
        origin_lat/origin_lng: Coordenadas do carro
        candidates: Todos os prestadores geocodificados
        top_n: Número de resultados finais
        pre_filter: Quantos candidatos passar para o OSRM após Haversine
        osrm_delay: Delay entre chamadas OSRM

    Returns:
        Lista com os top_n prestadores mais próximos, com chave 'road_km'.
    """
    # Etapa 1: Pré-filtro Haversine
    shortlist = top_n_haversine(origin_lat, origin_lng, candidates, n=pre_filter)

    if not shortlist:
        return []

    # Etapa 2: Distância por estrada
    with_road = osrm_road_distances(
        origin_lat, origin_lng, shortlist, delay_seconds=osrm_delay
    )

    # Ordenar por distância por estrada e retornar top N
    with_road.sort(key=lambda x: (x.get("road_km") is None, x.get("road_km", 9999)))
    return with_road[:top_n]
