import requests


def check_health(base_url: str) -> bool:
    """
    Verifica che il container sia attivo, rimuovendo /v1 se presente.
    """
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False
