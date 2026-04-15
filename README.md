# 🤖 Bot Telegram — Sourcing Luxe
## Guide de déploiement complet (gratuit, ~15 min)

---

## ÉTAPE 1 — Créer le bot Telegram (2 min)

1. Ouvre Telegram → cherche **@BotFather**
2. Envoie : `/newbot`
3. Donne un nom : `Sourcing Luxe Bot`
4. Donne un username : `mon_sourcing_luxe_bot`
5. BotFather te donne un **TOKEN** (ex: `7412345678:AAF...`)
6. **Copie ce token**

Pour obtenir ton CHAT_ID :
1. Démarre le bot (clique sur le lien que BotFather t'envoie)
2. Envoie `/start`
3. Va sur : `https://api.telegram.org/bot<TON_TOKEN>/getUpdates`
4. Trouve le champ `"id"` dans `"chat"` → c'est ton CHAT_ID

---

## ÉTAPE 2 — Configurer le bot (1 min)

Ouvre `config.py` et remplace :
```python
TELEGRAM_TOKEN = "COLLE_TON_TOKEN_ICI"
CHAT_ID        = "COLLE_TON_CHAT_ID_ICI"
```

---

## ÉTAPE 3 — Mettre sur GitHub (5 min)

1. Crée un compte sur **github.com** (gratuit)
2. Clique sur **"New repository"**
3. Nom : `sourcing-luxe-bot` → **Create repository**
4. Clique sur **"uploading an existing file"**
5. Glisse tous les fichiers du dossier :
   - `main.py`
   - `config.py`
   - `scrapers.py`
   - `database.py`
   - `requirements.txt`
6. Clique **"Commit changes"**

---

## ÉTAPE 4 — Déployer sur Render.com (5 min)

1. Crée un compte sur **render.com** (gratuit)
2. Clique **"New +"** → **"Web Service"**
3. Connecte ton compte GitHub → sélectionne `sourcing-luxe-bot`
4. Configure :
   - **Name** : `sourcing-luxe-bot`
   - **Runtime** : `Python 3`
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `python main.py`
   - **Instance Type** : `Free`
5. Clique **"Create Web Service"**
6. Le bot démarre en ~2 min ✅

---

## COMMANDES DISPONIBLES

| Commande | Action |
|---|---|
| `/start` | Démarrage + aide |
| `/scan` | Lance un scan immédiat sur toutes les marques |
| `/pepites` | Affiche les pépites du dernier scan |
| `/marque Brioni` | Cherche une marque spécifique |
| `/favoris` | Tes articles favoris |
| `/stats` | Statistiques du bot |
| `/reset` | Vide le cache (pour re-scanner tout) |

---

## FORMAT DES ALERTES

Chaque alerte contient :
- 📸 Photo de l'article
- Titre complet
- Plateforme (Vinted / Vestiaire / eBay / Leboncoin)
- Prix d'achat
- Prix de revente estimé
- Marge en %
- 🔗 **Lien direct cliquable vers l'article**
- Bouton ⭐ pour ajouter aux favoris

---

## DÉPANNAGE

**Le bot ne répond pas ?**
→ Vérifie le TOKEN dans `config.py`
→ Vérifie que le service Render est bien "Running"

**Pas d'articles trouvés ?**
→ Lance `/reset` pour vider le cache
→ Vinted peut bloquer temporairement → attends 1h

**Render s'endort ?**
→ Plan gratuit : le service dort après 15 min sans requête
→ Solution : ajouter un "Health Check" sur Render ou upgrader à $7/mois
→ Alternative gratuite : utiliser **Railway.app** (500h/mois gratuites)
