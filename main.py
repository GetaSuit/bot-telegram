"""
main.py — Bot Telegram Sourcing Luxe
────────────────────────────────────
Commandes disponibles :
  /start       → Bienvenue + aide
  /scan        → Lance un scan immédiat
  /pepites     → Affiche les pépites du dernier scan
  /marque Brioni → Recherche une marque spécifique
  /favoris     → Liste tes articles favoris
  /stats       → Statistiques du bot
  /reset       → Vide le cache des articles vus
  /aide        → Rappel des commandes
"""

import logging
import asyncio
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
from scrapers import scrape_all, scrape_vinted, scrape_vestiaire, scrape_ebay, scrape_leboncoin
from config import (
    TELEGRAM_TOKEN, CHAT_ID, SCAN_INTERVAL_MIN,
    ALL_BRANDS, FORBIDDEN_MATERIALS, NOBLE_MATERIALS,
    get_tier, estimated_sell_price, margin_pct, is_pepite,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# ── Statistiques en mémoire ───────────────────────────────
stats = {
    "scans": 0,
    "articles_found": 0,
    "pepites_found": 0,
    "last_scan": None,
}

last_scan_results: list[dict] = []


# ─────────────────────────────────────────────────────────────────
#  FILTRAGE & ENRICHISSEMENT
# ─────────────────────────────────────────────────────────────────

def _has_forbidden_material(item: dict) -> bool:
    text = (item.get("title", "") + " " + item.get("description", "")).lower()
    return any(m in text for m in FORBIDDEN_MATERIALS)


def _size_ok(item: dict) -> bool:
    size = item.get("size", "").strip()
    if not size:
        return True  # pas de taille → on laisse passer
    all_sizes = config.SIZES_MEN + config.SIZES_WOMEN
    return any(s.lower() in size.lower() for s in all_sizes)


def _enrich(item: dict) -> dict:
    """Ajoute tier, marge estimée, flag pépite."""
    brand = item.get("brand", "")
    tier  = get_tier(brand)
    buy   = item["price"]
    sell  = estimated_sell_price(buy, tier)
    marge = margin_pct(buy, tier)
    pep   = is_pepite(buy, tier)

    item["tier"]            = tier
    item["sell_estimated"]  = sell
    item["margin_pct"]      = marge
    item["pepite"]          = pep
    return item


def filter_and_enrich(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        if _has_forbidden_material(it):
            continue
        if not _size_ok(it):
            continue
        if db.is_seen(it["url"]):
            continue
        it = _enrich(it)
        out.append(it)
    return out


# ─────────────────────────────────────────────────────────────────
#  FORMATEUR DE MESSAGES TELEGRAM
# ─────────────────────────────────────────────────────────────────

PLATFORM_EMOJI = {
    "Vinted":               "🟢",
    "Vestiaire Collective": "⚫",
    "eBay":                 "🔵",
    "Leboncoin":            "🟠",
}

TIER_LABEL = {"T1": "⭐ Sartorial", "T2": "✦ Grand luxe", "T3": "◆ Luxe"}


def format_item_message(item: dict) -> str:
    pep_line  = "🔥 *PÉPITE DÉTECTÉE* 🔥\n\n" if item["pepite"] else ""
    platform  = item["platform"]
    emoji_pl  = PLATFORM_EMOJI.get(platform, "•")
    tier_lbl  = TIER_LABEL.get(item["tier"], "")

    lines = [
        pep_line,
        f"*{item['title']}*\n",
        f"{emoji_pl} {platform}  |  {tier_lbl}\n",
        f"💰 Achat : *{item['price']:.0f} €*\n",
        f"📈 Revente estimée : *{item['sell_estimated']} €*\n",
        f"📊 Marge : *+{item['margin_pct']}%*\n",
    ]
    if item.get("size"):
        lines.append(f"📐 Taille : {item['size']}\n")
    lines.append(f"\n🔗 [Voir l'article]({item['url']})")
    return "".join(lines)


def item_keyboard(item: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ Ajouter aux favoris", callback_data=f"fav|{item['url']}|{item['title']}"),
            InlineKeyboardButton("🔗 Ouvrir", url=item["url"]),
        ]
    ])


# ─────────────────────────────────────────────────────────────────
#  ENVOI D'UNE ALERTE
# ─────────────────────────────────────────────────────────────────

async def send_item_alert(app: Application, item: dict):
    text    = format_item_message(item)
    keyboard = item_keyboard(item)
    chat    = CHAT_ID

    try:
        if item.get("image_url"):
            await app.bot.send_photo(
                chat_id   = chat,
                photo     = item["image_url"],
                caption   = text,
                parse_mode= ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
        else:
            await app.bot.send_message(
                chat_id   = chat,
                text      = text,
                parse_mode= ParseMode.MARKDOWN,
                reply_markup=keyboard,
                disable_web_page_preview=False,
            )
        db.mark_seen(item["url"], item["title"])
    except Exception as e:
        log.error(f"Erreur envoi alerte: {e}")
        # Fallback sans image
        try:
            await app.bot.send_message(
                chat_id=chat, text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
            db.mark_seen(item["url"], item["title"])
        except Exception as e2:
            log.error(f"Fallback aussi échoué: {e2}")


# ─────────────────────────────────────────────────────────────────
#  SCAN PRINCIPAL
# ─────────────────────────────────────────────────────────────────

async def run_scan(app: Application, brands: list[str] = None, silent: bool = False):
    global last_scan_results
    target_brands = brands or ALL_BRANDS
    stats["scans"] += 1
    stats["last_scan"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    if not silent:
        await app.bot.send_message(
            CHAT_ID,
            f"🔍 Scan en cours sur {len(target_brands)} marques...\n"
            f"Plateformes : Vinted · Vestiaire · eBay · Leboncoin"
        )

    all_items  = []
    new_items  = []
    pepites    = []

    for brand in target_brands:
        raw = scrape_all(brand, max_price=2000)
        filtered = filter_and_enrich(raw)
        all_items.extend(filtered)
        for it in filtered:
            if it["pepite"]:
                pepites.append(it)
            else:
                new_items.append(it)

    # Trier pépites en premier, puis par marge décroissante
    pepites.sort(key=lambda x: x["margin_pct"], reverse=True)
    new_items.sort(key=lambda x: x["margin_pct"], reverse=True)
    ordered = pepites + new_items
    last_scan_results = ordered

    stats["articles_found"] += len(ordered)
    stats["pepites_found"]  += len(pepites)

    if not ordered:
        if not silent:
            await app.bot.send_message(CHAT_ID, "✅ Scan terminé — aucun nouvel article trouvé.")
        return

    # Résumé
    summary = (
        f"✅ *Scan terminé*\n\n"
        f"📦 Nouveaux articles : *{len(ordered)}*\n"
        f"🔥 Pépites : *{len(pepites)}*\n\n"
        f"Envoi des alertes..."
    )
    await app.bot.send_message(CHAT_ID, summary, parse_mode=ParseMode.MARKDOWN)

    # Envoyer pépites en premier
    for item in pepites[:10]:
        await send_item_alert(app, item)
        await asyncio.sleep(0.5)

    # Puis les autres (max 20 pour ne pas spammer)
    for item in new_items[:20]:
        await send_item_alert(app, item)
        await asyncio.sleep(0.5)


# ─────────────────────────────────────────────────────────────────
#  COMMANDES TELEGRAM
# ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"👔 *Bot Sourcing Luxe*\n\n"
        f"Ton chat ID : `{chat_id}`\n\n"
        f"*Commandes disponibles :*\n"
        f"/scan — Lance un scan immédiat\n"
        f"/pepites — Affiche les pépites du dernier scan\n"
        f"/marque Brioni — Cherche une marque spécifique\n"
        f"/favoris — Tes articles favoris\n"
        f"/stats — Statistiques\n"
        f"/reset — Vide le cache\n"
        f"/aide — Cette aide",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Scan lancé...")
    await run_scan(ctx.application)


async def cmd_pepites(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pepites = [it for it in last_scan_results if it.get("pepite")]
    if not pepites:
        await update.message.reply_text(
            "Aucune pépite dans le dernier scan. Lance /scan pour actualiser."
        )
        return
    await update.message.reply_text(f"🔥 *{len(pepites)} pépite(s)* trouvée(s) :", parse_mode=ParseMode.MARKDOWN)
    for it in pepites[:10]:
        await send_item_alert(ctx.application, it)
        await asyncio.sleep(0.4)


async def cmd_marque(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage : /marque NomDeLaMarque\nEx : /marque Brioni")
        return
    brand = " ".join(ctx.args)
    await update.message.reply_text(f"🔍 Recherche *{brand}* sur toutes les plateformes...", parse_mode=ParseMode.MARKDOWN)
    raw      = scrape_all(brand, max_price=2000)
    filtered = filter_and_enrich(raw)
    filtered.sort(key=lambda x: x["margin_pct"], reverse=True)
    if not filtered:
        await update.message.reply_text(f"Aucun article trouvé pour *{brand}*.", parse_mode=ParseMode.MARKDOWN)
        return
    await update.message.reply_text(f"✅ *{len(filtered)} article(s)* trouvé(s) pour *{brand}* :", parse_mode=ParseMode.MARKDOWN)
    for it in filtered[:8]:
        await send_item_alert(ctx.application, it)
        await asyncio.sleep(0.4)


async def cmd_favoris(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    favs = db.list_favorites()
    if not favs:
        await update.message.reply_text("Tu n'as pas encore de favoris.\nClique sur ⭐ sous un article pour en ajouter.")
        return
    await update.message.reply_text(f"⭐ *Tes {len(favs)} favori(s) :*", parse_mode=ParseMode.MARKDOWN)
    for it in favs:
        text = (
            f"*{it['title']}*\n"
            f"💰 {it['price']:.0f}€ → ~{it.get('sell_estimated', '?')}€\n"
            f"📊 +{it.get('margin_pct', '?')}%\n"
            f"🔗 [Voir]({it['url']})"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑 Retirer des favoris", callback_data=f"unfav|{it['url']}"),
            InlineKeyboardButton("🔗 Ouvrir", url=it["url"]),
        ]])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        await asyncio.sleep(0.3)


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    favs = db.list_favorites()
    msg = (
        f"📊 *Statistiques du bot*\n\n"
        f"🔍 Scans effectués : {stats['scans']}\n"
        f"📦 Articles analysés : {stats['articles_found']}\n"
        f"🔥 Pépites trouvées : {stats['pepites_found']}\n"
        f"⭐ Favoris : {len(favs)}\n"
        f"🕐 Dernier scan : {stats['last_scan'] or 'jamais'}\n"
        f"⏱ Scan auto toutes les {SCAN_INTERVAL_MIN} min"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db.clear_seen()
    await update.message.reply_text("✅ Cache vidé — le prochain scan renverra tous les articles.")


async def cmd_aide(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


# ─────────────────────────────────────────────────────────────────
#  CALLBACKS BOUTONS INLINE
# ─────────────────────────────────────────────────────────────────

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("fav|"):
        _, url, title = data.split("|", 2)
        # Trouver l'item complet dans les résultats
        item = next((it for it in last_scan_results if it["url"] == url), None)
        if not item:
            item = {"url": url, "title": title, "price": 0}
        added = db.add_favorite(item)
        if added:
            await query.edit_message_reply_markup(
                InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Ajouté aux favoris", callback_data="noop"),
                    InlineKeyboardButton("🔗 Ouvrir", url=url),
                ]])
            )
        else:
            await query.answer("Déjà dans tes favoris !")

    elif data.startswith("unfav|"):
        _, url = data.split("|", 1)
        db.remove_favorite(url)
        await query.edit_message_reply_markup(
            InlineKeyboardMarkup([[
                InlineKeyboardButton("🗑 Retiré", callback_data="noop"),
            ]])
        )


# ─────────────────────────────────────────────────────────────────
#  LANCEMENT
# ─────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commandes
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("scan",    cmd_scan))
    app.add_handler(CommandHandler("pepites", cmd_pepites))
    app.add_handler(CommandHandler("marque",  cmd_marque))
    app.add_handler(CommandHandler("favoris", cmd_favoris))
    app.add_handler(CommandHandler("stats",   cmd_stats))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(CommandHandler("aide",    cmd_aide))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Scheduler — scan automatique
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: asyncio.create_task(run_scan(app, silent=True)),
        "interval",
        minutes=SCAN_INTERVAL_MIN,
        id="auto_scan",
    )
    scheduler.start()

    log.info(f"Bot démarré — scan toutes les {SCAN_INTERVAL_MIN} min")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
