# Météorologue IA 🌦️

Chatbot web en français qui répond comme un **prévisionniste professionnel** en croisant des modèles numériques et des observations en temps réel. Pour chaque question météo, il :

- Croise **deux modèles numériques** de Météo-France (**AROME** haute résolution et **ARPEGE** moyenne échéance) via Open-Meteo ;
- **Détaille son raisonnement (Chain of Thought - CoT)** dans un bloc pliable pour les technophiles ;
- **Chiffre leur accord ou leur divergence** et l'explique ;
- Intègre les **observations temps réel** du réseau de stations **Infoclimat** pour caler le présent (nowcasting) ;
- Explique le **« pourquoi » météo** (flux, front, anticyclone, instabilité/CAPE…) ;
- Rappelle les **limites des modèles** (AROME surtout < 48 h, ARPEGE au-delà) ;
- Assortit toujours sa réponse d'un **niveau de confiance** (élevé / modéré / faible) ;
- **N'invente jamais** une donnée : si une mesure manque, il le signale.

---

## 🚀 Fonctionnalités Améliorées

1. **Raisonnement pliable (Chain of Thought)** : L'analyse intermédiaire du prévisionniste est encapsulée dans un bloc pliable HTML `<details>` afin de ne pas surcharger la lecture pour le grand public, tout en restant accessible d'un simple clic.
2. **Sélection dynamique des stations (StatIC)** : Charge 1195 stations associatives depuis un fichier GeoJSON local (`app/stations.geojson`). Cela permet de géolocaliser automatiquement la station la plus proche et de supporter les **clés API Infoclimat gratuites** (les clés gratuites n'étant pas autorisées à interroger les stations SYNOP Météo-France).
3. **Conversion horaire automatique** : Les heures d'observations d'Infoclimat (retournées en UTC) sont automatiquement traduites dans le fuseau `Europe/Paris` (heure locale) par le serveur avant d'être analysées par le LLM pour éliminer toute confusion de fuseau horaire.
4. **Interface moderne avec rendu Markdown** : L'interface web de discussion intègre la bibliothèque `marked` côté client pour un rendu impeccable des gras, listes et tableaux générés par le prévisionniste.

---

## 🛠️ Architecture

```
Question utilisateur
      │
      ▼
[1] Extraction d'intention (LLM)  ──► Localisation, échéance, type de demande
      │
      ▼
[2] Géocodage (Open-Meteo)        ──► Latitude / Longitude
      │
      ▼
[3] Récupération EN PARALLÈLE :
      • AROME  (arome_france_hd)  ┐
      • ARPEGE (arpege_europe)    ├─ Open-Meteo (endpoint Météo-France)
      • Observations Infoclimat   ┘  (Sélection dynamique de la station StatIC la plus proche)
      │
      ▼
[4] Bloc de données structuré (JSON) + conversion UTC -> Heure locale Paris
      │
      ▼
[5] Réponse du prévisionniste (LLM, avec CoT pliable + réponse finale)
```

- **Backend** : Python 3.11+ / FastAPI (`app/`).
- **Frontend** : Page de chat unique servie statiquement (`app/static/`) avec gestion du Markdown.
- **LLM** : API OpenAI (clé lue dans l'environnement, modèle configurable).

---

## 📋 Prérequis

- Python 3.11+ (testé en 3.11 et 3.12)
- Une clé API OpenAI (compte standard ou de service)

---

## ⚙️ Installation

1. **Cloner le projet** :
   ```bash
   git clone https://github.com/BenjaminPolge/meteorologue-ia.git
   cd meteorologue-ia
   ```

2. **Créer et activer l'environnement virtuel** :
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Sous Windows : .venv\Scripts\activate
   ```

3. **Installer les dépendances** :
   ```bash
   pip install -r requirements.txt
   ```

---

## 🔧 Configuration

Copiez le fichier de configuration d'exemple :
```bash
cp .env.example .env
```

Éditez le fichier `.env` pour y renseigner vos variables :

| Variable | Obligatoire | Description |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | Clé API OpenAI. |
| `OPENAI_MODEL` | ➖ | Modèle OpenAI à utiliser (ex: `gpt-4o`). Défaut : `gpt-5.5` |
| `OPENAI_BASE_URL` | ➖ | Base URL optionnelle (pour Azure ou proxy OpenAI). |
| `INFOCLIMAT_TOKEN` | ➖ | Jeton de l'[API publique Infoclimat](https://www.infoclimat.fr/public-api/). Nécessaire pour inclure les observations réelles. |
| `INFOCLIMAT_STATIONS` | ➖ | Permet de forcer une liste d'identifiants de stations (ex: `000B3,00004`). Par défaut, la station compatible la plus proche est sélectionnée. |
| `HTTP_TIMEOUT` | ➖ | Délai d'expiration HTTP en secondes (défaut : 20). |

---

## 🎈 Lancement

Pour lancer le serveur de développement :
```bash
uvicorn app.main:app --reload --port 8000
```
Puis ouvrez votre navigateur à l'adresse suivante : **[http://localhost:8000](http://localhost:8000)**.

### Vérification rapide
Pour vérifier que la configuration est bien chargée par le serveur :
```bash
curl http://localhost:8000/api/health
```

---

## 💬 Exemples de Questions

- *« Quel temps fait-il là maintenant à Paris ? »*
- *« Risque d'orage cette après-midi sur Lille ? »*
- *« AROME et ARPEGE sont-ils d'accord pour Lyon demain ? »*
- *« Va-t-il pleuvoir demain après-midi à Serris ? »*
