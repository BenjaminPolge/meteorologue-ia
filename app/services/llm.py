"""Intégration OpenAI : extraction d'intention + génération de la réponse.

La clé est lue dans OPENAI_API_KEY (jamais codée en dur). Le modèle est
configurable via OPENAI_MODEL (défaut : gpt-5.5).
"""
from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.prompts import EXTRACTION_SYSTEM_PROMPT, METEOROLOGIST_SYSTEM_PROMPT

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY n'est pas définie dans l'environnement."
            )
        kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        _client = AsyncOpenAI(**kwargs)
    return _client


def _parse_json_object(text: str) -> dict[str, Any]:
    """Extrait le premier objet JSON d'une chaîne, de façon tolérante."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


async def extract_intent(
    history: list[dict[str, str]], now_iso: str
) -> dict[str, Any]:
    """Détermine localisation, échéance et type de demande à partir du dialogue."""
    client = get_client()
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    user_block = (
        f"Date et heure actuelles (Europe/Paris) : {now_iso}.\n\n"
        f"Conversation :\n{convo}\n\n"
        "Renvoie l'intention au format JSON."
    )
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_block},
        ],
    )
    content = resp.choices[0].message.content or "{}"
    return _parse_json_object(content)


async def generate_answer(
    history: list[dict[str, str]], data_block: dict[str, Any]
) -> str:
    """Génère la réponse du prévisionniste à partir du bloc de données structuré."""
    client = get_client()
    data_json = json.dumps(data_block, ensure_ascii=False, indent=2)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": METEOROLOGIST_SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                "Voici le bloc de données structuré (modèles AROME/ARPEGE via "
                "Open-Meteo et observations Infoclimat). Utilise EXCLUSIVEMENT "
                "ces données chiffrées. Si un champ vaut null ou est absent, "
                "considère la donnée comme indisponible et dis-le.\n\n"
                f"```json\n{data_json}\n```"
            ),
        },
    ]
    messages.extend(history)
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
    )
    return resp.choices[0].message.content or ""
