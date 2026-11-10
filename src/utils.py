import requests


def check_health(base_url: str, model: str) -> None:
    """
    Verifica che il server sia raggiungibile e serva il modello richiesto
    (GET /v1/models, disponibile sia su vLLM sia su llama.cpp).
    """
    try:
        response = requests.get(f"{base_url}/v1/models", timeout=5)
        response.raise_for_status()
        served_models = [m["id"] for m in response.json()["data"]]
    except (requests.RequestException, KeyError, ValueError):
        raise SystemExit(
            f"LLM engine is not reachable at {base_url}. "
            "Start the server before running this script."
        )

    if model not in served_models:
        raise SystemExit(
            f"Model '{model}' is not served at {base_url}. "
            f"Served models: {', '.join(served_models) or 'none'}."
        )
