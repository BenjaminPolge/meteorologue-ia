# Météorologue IA 🌦️

Chatbot web en français qui répond comme un **prévisionniste professionnel**, et
non comme un simple bulletin. Pour chaque question, il :

- croise **deux modèles numériques** Météo-France (**AROME** haute résolution et
  **ARPEGE** moyenne échéance) via Open-Meteo ;
- **chiffre leur accord ou leur divergence** et l'explique ;
- intègre les **observations temps réel** du réseau de stations **Infoclimat**
  pour caler le présent (nowcasting) ;
- explique le **« pourquoi » météo** (flux, front, anticyclone, instabilité/CAPE…) ;
- rappelle les **limites des modèles** (AROME surtout < 48 h, ARPEGE au-delà,
  fiabilité décroissante avec l'échéance) ;
- assortit toujours sa réponse d'un **niveau de confiance** (élevé / modéré / faible) ;
- **n'invente jamais** une donnée : si une mesure manque, il le dit.

## Architecture

```
Question utilisateur
      │
      ▼
[1] Extraction d'intention (LLM)  ──► localisation, échéance, type de demande
      │
      ▼
[2] Géocodage (Open-Meteo)        ──► latitude / longitude
      │
      ▼
[3] Récupération EN PARALLÈLE :
      • AROME  (arome_france_hd)  ┐
      • ARPEGE (arpege_europe)    ├─ Open-Meteo (endpoint Météo-France)
      • Observations Infoclimat   ┘
      │
      ▼
[4] Bloc de données structuré (JSON) + calcul accord/divergence des modèles
      │
      ▼
[5] Réponse du prévisionniste (LLM, system prompt « météorologue »)
```

- **Backend** : Python + FastAPI (`app/`).
- **Frontend** : page de chat unique servie statiquement (`app/static/`).
- **LLM** : API OpenAI (clé lue dans l'environnement, modèle configurable).

### Données récupérées par échéance horaire
Température 2 m, précipitations (+ probabilité quand le modèle l'expose), vent et
rafales 10 m, couverture nuageuse, pression au niveau mer, humidité relative,
CAPE. L'app calcule des synthèses par fenêtre et par jour, ainsi qu'un objet
`accord_modeles` (écarts chiffrés AROME vs ARPEGE).

## Prérequis

- Python 3.11+ (testé en 3.12)
- Une clé API OpenAI

## Installation

```bash
git clone <URL_DU_REPO>
cd meteorologue-ia

python3 -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration (variables d'environnement)

Copiez le modèle puis renseignez vos clés :

```bash
cp .env.example .env
# éditez .env
```

| Variable | Obligatoire | Description |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | Clé API OpenAI (jamais codée en dur). |
| `OPENAI_MODEL` | ➖ | Modèle à utiliser. Défaut : `gpt-5.5`. Mettez un modèle disponible sur votre compte si besoin (`gpt-4o`, `gpt-4.1`, `gpt-5`, …). |
| `OPENAI_BASE_URL` | ➖ | Base URL personnalisée (proxy / endpoint compatible OpenAI). |
| `INFOCLIMAT_TOKEN` | ➖ | Token de l'[API publique Infoclimat](https://www.infoclimat.fr/public-api/). Sans lui, l'app fonctionne mais indique que les observations ne sont pas disponibles. |
| `INFOCLIMAT_STATIONS` | ➖ | Liste d'IDs de stations à forcer (séparés par des virgules). Par défaut, la station SYNOP la plus proche est choisie automatiquement. |
| `HTTP_TIMEOUT` | ➖ | Délai d'expiration HTTP en secondes (défaut 20). |

> **Open-Meteo (AROME/ARPEGE) et le géocodage ne nécessitent aucune clé.**

## Lancement

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Puis ouvrez **http://localhost:8000**.

Vérification rapide de la configuration :

```bash
curl http://localhost:8000/api/health
```

## API

`POST /api/chat`

```json
{
  "messages": [{ "role": "user", "content": "Va-t-il pleuvoir demain après-midi à Serris ?" }],
  "include_data": false
}
```

Réponse :

```json
{ "answer": "…analyse du prévisionniste…", "needs_location": false, "data_block": null }
```

Passez `"include_data": true` pour recevoir aussi le bloc de données structuré
utilisé par le LLM (utile pour le débogage).

## Exemples de questions

- « Va-t-il pleuvoir demain après-midi à Serris ? »
- « Risque d'orage cette semaine sur l'Île-de-France ? »
- « Quel temps fait-il là maintenant à Lille ? »
- « AROME et ARPEGE sont-ils d'accord pour Lyon demain ? »

## Limitations connues

- **Probabilité de précipitations** : les modèles Météo-France AROME/ARPEGE
  n'exposent pas ce champ via Open-Meteo (valeur `null`). L'app le signale au
  lieu de l'inventer.
- **Infoclimat & Cloudflare** : le domaine `infoclimat.fr` est protégé par
  Cloudflare. Depuis certaines IP de datacenter, les requêtes peuvent être
  bloquées (HTTP 403 / « Just a moment »). Dans ce cas l'app le détecte et
  l'indique clairement ; l'appel fonctionne normalement depuis une IP non
  filtrée, avec un token valide.
```
