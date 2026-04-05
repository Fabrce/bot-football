import os
import math
import hashlib
import logging
import random
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

ASK_HOME, ASK_AWAY = range(2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"Bonjour {user.mention_html()} ! Je suis ton bot football 🏟️\n\n"
        "Voici ce que je peux faire :\n"
        "/start — Afficher ce message d'accueil\n"
        "/help — Obtenir de l'aide\n"
        "/predict — Prédire le résultat d'un match\n"
        "/echo &lt;texte&gt; — Répéter ton texte\n\n"
        "Envoie-moi n'importe quel message et je te répondrai !"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Commandes disponibles :\n"
        "/start — Démarrer le bot\n"
        "/help — Afficher ce message d'aide\n"
        "/predict — Prédire le résultat d'un match de football\n"
        "/echo <texte> — Répéter ton texte\n\n"
        "Tu peux aussi m'envoyer n'importe quel message !"
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        text = " ".join(context.args)
        await update.message.reply_text(f"Echo : {text}")
    else:
        await update.message.reply_text("Utilisation : /echo <ton texte ici>")


def _poisson_prob(lam: float, k: int) -> float:
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _exact_score(home_xg: float, away_xg: float, max_goals: int = 5) -> tuple[int, int, float]:
    best_score = (0, 0)
    best_prob = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            prob = _poisson_prob(home_xg, h) * _poisson_prob(away_xg, a)
            if prob > best_prob:
                best_prob = prob
                best_score = (h, a)
    return best_score[0], best_score[1], round(best_prob * 100, 1)


def _generate_prediction(home_team: str, away_team: str) -> dict:
    seed_str = f"{home_team.lower().strip()}vs{away_team.lower().strip()}"
    seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)

    home_base = rng.uniform(30, 55)
    draw_base = rng.uniform(20, 32)
    away_base = 100 - home_base - draw_base

    total = home_base + draw_base + away_base
    home_pct = round(home_base / total * 100, 1)
    draw_pct = round(draw_base / total * 100, 1)
    away_pct = round(100 - home_pct - draw_pct, 1)

    btts_pct = round(rng.uniform(38, 72), 1)

    home_goals = round(rng.uniform(0.8, 2.5), 1)
    away_goals = round(rng.uniform(0.6, 2.0), 1)

    score_home, score_away, score_prob = _exact_score(home_goals, away_goals)

    total_xg = home_goals + away_goals
    if total_xg < 1.5:
        goals_label = "Moins de 1.5 but"
        goals_emoji = "🔒"
    elif total_xg <= 2.5:
        goals_label = "Entre 1.5 et 2.5 buts"
        goals_emoji = "⚖️"
    else:
        goals_label = "Plus de 2.5 buts"
        goals_emoji = "🔥"

    if home_pct >= draw_pct and home_pct >= away_pct:
        verdict = f"Victoire {home_team}"
        verdict_emoji = "🔵"
    elif draw_pct >= home_pct and draw_pct >= away_pct:
        verdict = "Match nul"
        verdict_emoji = "🟡"
    else:
        verdict = f"Victoire {away_team}"
        verdict_emoji = "🔴"

    return {
        "home_pct": home_pct,
        "draw_pct": draw_pct,
        "away_pct": away_pct,
        "btts_pct": btts_pct,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "score_home": score_home,
        "score_away": score_away,
        "score_prob": score_prob,
        "goals_label": goals_label,
        "goals_emoji": goals_emoji,
        "verdict": verdict,
        "verdict_emoji": verdict_emoji,
    }


def _bar(pct: float, width: int = 20) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


async def predict_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "⚽ *Prédiction de match*\n\n"
        "Quel est le nom de l'équipe à domicile ?",
        parse_mode="Markdown"
    )
    return ASK_HOME


async def predict_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["home_team"] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ Équipe domicile : *{context.user_data['home_team']}*\n\n"
        "Quel est le nom de l'équipe visiteuse ?",
        parse_mode="Markdown"
    )
    return ASK_AWAY


async def predict_away(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    home_team = context.user_data.get("home_team", "Domicile")
    away_team = update.message.text.strip()
    context.user_data.clear()

    p = _generate_prediction(home_team, away_team)

    msg = (
        f"🏟️ *{home_team}* vs *{away_team}*\n"
        f"{'─' * 30}\n\n"
        f"📊 *Probabilités de résultat*\n\n"
        f"🏠 Victoire {home_team}\n"
        f"`{_bar(p['home_pct'])}` {p['home_pct']}%\n\n"
        f"🤝 Match nul\n"
        f"`{_bar(p['draw_pct'])}` {p['draw_pct']}%\n\n"
        f"✈️ Victoire {away_team}\n"
        f"`{_bar(p['away_pct'])}` {p['away_pct']}%\n\n"
        f"{'─' * 30}\n"
        f"⚽ *Les deux équipes marquent (BTTS)*\n"
        f"`{_bar(p['btts_pct'])}` {p['btts_pct']}%\n\n"
        f"{'─' * 30}\n"
        f"🎯 *Buts attendus*\n"
        f"  🏠 {home_team} : {p['home_goals']} but(s)\n"
        f"  ✈️ {away_team} : {p['away_goals']} but(s)\n\n"
        f"{'─' * 30}\n"
        f"🔢 *Score exact le plus probable*\n"
        f"  ➡️ *{p['score_home']} - {p['score_away']}*  ({p['score_prob']}% de probabilité)\n\n"
        f"{'─' * 30}\n"
        f"{p['goals_emoji']} *Total de buts : {p['goals_label']}*\n\n"
        f"{'─' * 30}\n"
        f"{p['verdict_emoji']} *Pronostic : {p['verdict']}*\n\n"
        f"_⚠️ Ces prédictions sont générées algorithmiquement et ne constituent pas des conseils de paris._"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")
    return ConversationHandler.END


async def predict_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Prédiction annulée.")
    return ConversationHandler.END


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    user = update.effective_user.first_name
    logger.info(f"Message de {user}: {text}")
    await update.message.reply_text(
        f"Tu as dit : {text}\n\nUtilise /help pour voir les commandes disponibles."
    )


def main() -> None:
    if not TOKEN:
        raise ValueError("La variable d'environnement TELEGRAM_BOT_TOKEN n'est pas définie !")

    app = Application.builder().token(TOKEN).build()

    predict_conv = ConversationHandler(
        entry_points=[CommandHandler("predict", predict_start)],
        states={
            ASK_HOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_home)],
            ASK_AWAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, predict_away)],
        },
        fallbacks=[CommandHandler("cancel", predict_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("echo", echo))
    app.add_handler(predict_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot en cours d'exécution...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
