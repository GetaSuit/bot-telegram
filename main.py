"""
main.py — Bot Telegram Sourcing Luxe (version corrigée)
"""

import logging
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

import config
import database as db
from scrapers import scrape_all
from config import (
    TELEGRAM_TOKEN, CHAT_ID, SCAN_INTERVAL_MIN,
    ALL_BRANDS, FORBIDDEN_MATERIALS,
    get_tier, estimated_sell_price, margin_pct, is_pepite,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger(__name__)

stats = {"scans": 0, "articles_found": 0, "pepites_found": 0, "last_scan": None}
last_scan_results: list[dict] = []

PLATFORM_EMOJI = {"Vinted": "🟢", "Vestiaire Collective": "⚫", "eBay": "🔵", "Leboncoin": "🟠"}
TIER_LABEL = {"T1": "⭐ Sartorial", "T2": "✦ Grand luxe", "T3": "◆ Luxe"}

def _has_forbidden_material(item):
    text = (item.get("title", "") + " " + item.get("description", "")).lower()
    return any(m in text for m in FORBIDDEN_MATERIALS)

def _size_ok(item):
    size = item.get("size", "").strip()
    if not size:
        return True
    return any(s.lower() in size.lower() for s in config.SIZES_MEN + config.SIZES_WOMEN)

def _enrich(item):
    tier = get_tier(item.get("brand", ""))
    buy  = item["price"]
    item["tier"] = tier
    item["sell_estimated"] = estimated_sell_price(buy, tier)
    item["margin_pct"] = margin_pct(buy, tier)
    item["pepite"] = is_pepite(buy, tier)
    return item

def filter_and_enrich(items):
    out = []
    for it in items:
        if _has_forbidden_material(it): continue
        if not _size_ok(it): continue
        if db.is_seen(it["url"]): continue
        out.append(_enrich(it))
    return out

def format_item_message(item):
    pep  = "🔥 *PÉPITE DÉTECTÉE* 🔥\n\n" if item["pepite"] else ""
    pl   = PLATFORM_EMOJI.get(item["platform"], "•")
    tier = TIER_LABEL.get(item["tier"], "")
    msg  = (f"{pep}*{item['title']}*\n\n{pl} {item['platform']}  |  {tier}\n"
            f"💰 Achat : *{item['price']:.0f} €*\n"
            f"📈 Revente estimée : *{item['sell_estimated']} €*\n"
            f"📊 Marge : *+{item['margin_pct']}%*\n")
    if item.get("size"):
        msg += f"📐 Taille : {item['size']}\n"
    msg += f"\n🔗 [Voir l'article]({item['url']})"
    return msg

def item_keyboard(item):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⭐ Favori", callback_data=f"fav|{item['url']}|{item['title'][:40]}"),
        InlineKeyboardButton("🔗 Ouvrir", url=item["url"]),
    ]])

async def send_item_alert(app, item):
    text = format_item_message(item)
    kb   = item_keyboard(item)
    try:
        if item.get("image_url"):
            await app.bot.send_photo(chat_id=CHAT_ID, photo=item["image_url"],
                caption=text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        else:
            await app.bot.send_message(chat_id=CHAT_ID, text=text,
                parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        db.mark_seen(item["url"], item["title"])
    except Exception as e:
        log.error(f"Erreur envoi: {e}")
        try:
            await app.bot.send_message(chat_id=CHAT_ID, text=text,
                parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            db.mark_seen(item["url"], item["title"])
        except Exception as e2:
            log.error(f"Fallback échoué: {e2}")

async def run_scan(app, brands=None, silent=False):
    global last_scan_results
    target = brands or ALL_BRANDS
    stats["scans"] += 1
    stats["last_scan"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    if not silent:
        await app.bot.send_message(CHAT_ID,
            f"🔍 Scan en cours sur {len(target)} marques...\nPlateformes : Vinted · Vestiaire · eBay · Leboncoin")
    pepites, autres = [], []
    for brand in target:
        filtered = filter_and_enrich(scrape_all(brand, max_price=2000))
        for it in filtered:
            (pepites if it["pepite"] else autres).append(it)
    pepites.sort(key=lambda x: x["margin_pct"], reverse=True)
    autres.sort(key=lambda x: x["margin_pct"], reverse=True)
    ordered = pepites + autres
    last_scan_results = ordered
    stats["articles_found"] += len(ordered)
    stats["pepites_found"]  += len(pepites)
    if not ordered:
        if not silent:
            await app.bot.send_message(CHAT_ID, "✅ Scan terminé — aucun nouvel article trouvé.")
        return
    await app.bot.send_message(CHAT_ID,
        f"✅ *Scan terminé*\n\n📦 Articles : *{len(ordered)}*\n🔥 Pépites : *{len(pepites)}*\n\nEnvoi des alertes...",
        parse_mode=ParseMode.MARKDOWN)
    for it in pepites[:10]:
        await send_item_alert(app, it); await asyncio.sleep(0.5)
    for it in autres[:20]:
        await send_item_alert(app, it); await asyncio.sleep(0.5)

async def auto_scan_job(context: ContextTypes.DEFAULT_TYPE):
    await run_scan(context.application, silent=True)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👔 *Bot Sourcing Luxe*\n\nTon chat ID : `{update.effective_chat.id}`\n\n"
        f"/scan — Scan immédiat\n/pepites — Pépites du dernier scan\n"
        f"/marque Brioni — Cherche une marque\n/favoris — Tes favoris\n"
        f"/stats — Statistiques\n/reset — Vide le cache",
        parse_mode=ParseMode.MARKDOWN)

async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Scan lancé...")
    await run_scan(ctx.application)

async def cmd_pepites(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    peps = [it for it in last_scan_results if it.get("pepite")]
    if not peps:
        await update.message.reply_text("Aucune pépite. Lance /scan pour actualiser.")
        return
    await update.message.reply_text(f"🔥 *{len(peps)} pépite(s) :*", parse_mode=ParseMode.MARKDOWN)
    for it in peps[:10]:
        await send_item_alert(ctx.application, it); await asyncio.sleep(0.4)

async def cmd_marque(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage : /marque Brioni"); return
    brand = " ".join(ctx.args)
    await update.message.reply_text(f"🔍 Recherche *{brand}*...", parse_mode=ParseMode.MARKDOWN)
    filtered = filter_and_enrich(scrape_all(brand, max_price=2000))
    filtered.sort(key=lambda x: x["margin_pct"], reverse=True)
    if not filtered:
        await update.message.reply_text(f"Aucun article pour *{brand}*.", parse_mode=ParseMode.MARKDOWN); return
    await update.message.reply_text(f"✅ *{len(filtered)} article(s) :*", parse_mode=ParseMode.MARKDOWN)
    for it in filtered[:8]:
        await send_item_alert(ctx.application, it); await asyncio.sleep(0.4)

async def cmd_favoris(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    favs = db.list_favorites()
    if not favs:
        await update.message.reply_text("Pas encore de favoris — clique ⭐ sous un article."); return
    await update.message.reply_text(f"⭐ *{len(favs)} favori(s) :*", parse_mode=ParseMode.MARKDOWN)
    for it in favs:
        text = (f"*{it['title']}*\n💰 {it['price']:.0f}€ → ~{it.get('sell_estimated','?')}€  "
                f"📊 +{it.get('margin_pct','?')}%\n🔗 [Voir]({it['url']})")
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑 Retirer", callback_data=f"unfav|{it['url']}"),
            InlineKeyboardButton("🔗 Ouvrir", url=it["url"]),
        ]])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        await asyncio.sleep(0.3)

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 *Statistiques*\n\n🔍 Scans : {stats['scans']}\n📦 Articles : {stats['articles_found']}\n"
        f"🔥 Pépites : {stats['pepites_found']}\n⭐ Favoris : {len(db.list_favorites())}\n"
        f"🕐 Dernier scan : {stats['last_scan'] or 'jamais'}\n⏱ Auto toutes les {SCAN_INTERVAL_MIN} min",
        parse_mode=ParseMode.MARKDOWN)

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db.clear_seen()
    await update.message.reply_text("✅ Cache vidé.")

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    if data.startswith("fav|"):
        _, url, title = data.split("|", 2)
        item = next((it for it in last_scan_results if it["url"] == url), {"url": url, "title": title, "price": 0})
        if db.add_favorite(item):
            await query.edit_message_reply_markup(InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Ajouté", callback_data="noop"),
                InlineKeyboardButton("🔗 Ouvrir", url=url),
            ]]))
    elif data.startswith("unfav|"):
        _, url = data.split("|", 1)
        db.remove_favorite(url)
        await query.edit_message_reply_markup(InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑 Retiré", callback_data="noop"),
        ]]))

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("scan",    cmd_scan))
    app.add_handler(CommandHandler("pepites", cmd_pepites))
    app.add_handler(CommandHandler("marque",  cmd_marque))
    app.add_handler(CommandHandler("favoris", cmd_favoris))
    app.add_handler(CommandHandler("stats",   cmd_stats))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.job_queue.run_repeating(auto_scan_job, interval=SCAN_INTERVAL_MIN * 60, first=30)
    log.info(f"Bot démarré — scan toutes les {SCAN_INTERVAL_MIN} min")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
