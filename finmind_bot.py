import os
import json
import logging
import anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

# =============================================
# ВСТАВЬ СЮДА СВОИ КЛЮЧИ
# =============================================
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"
ANTHROPIC_API_KEY = "YOUR_ANTHROPIC_KEY"
# =============================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Хранилище данных пользователей (в памяти)
user_data = {}

def get_user(user_id: int):
    if user_id not in user_data:
        user_data[user_id] = {
            "transactions": [],
            "goals": [],
            "balance": 0,
            "history": []
        }
    return user_data[user_id]

def get_ai_response(user_id: int, user_message: str) -> str:
    user = get_user(user_id)
    
    # Формируем контекст пользователя
    context = f"""
Ты — FinMind AI, личный финансовый помощник для молодёжи Узбекистана.
Говори как умный друг — просто, понятно, по-русски.
Будь краток (максимум 3-4 предложения).

Данные пользователя:
- Баланс: {user['balance']:,} сум
- Транзакций: {len(user['transactions'])}
- Целей: {len(user['goals'])}

Последние транзакции:
{json.dumps(user['transactions'][-5:], ensure_ascii=False) if user['transactions'] else 'Пока нет'}

Цели:
{json.dumps(user['goals'], ensure_ascii=False) if user['goals'] else 'Пока нет'}

Если пользователь говорит о трате денег (например "потратил 50000 на еду") — 
обязательно ответи в формате JSON внутри тегов <tx>...</tx>:
<tx>{{"type":"expense","amount":50000,"category":"еда","description":"обед"}}</tx>

Если пользователь говорит о доходе (например "получил зарплату 2000000") — 
ответи в формате JSON внутри тегов <tx>...</tx>:
<tx>{{"type":"income","amount":2000000,"category":"зарплата","description":"зарплата"}}</tx>

Если пользователь хочет поставить цель (например "хочу накопить 500000 на книги") —
ответи в формате JSON внутри тегов <goal>...</goal>:
<goal>{{"name":"книги","target":500000,"saved":0}}</goal>
"""

    # Добавляем историю диалога
    messages = user["history"][-10:] + [{"role": "user", "content": user_message}]
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=context,
        messages=messages
    )
    
    reply = response.content[0].text
    
    # Обрабатываем транзакции
    if "<tx>" in reply and "</tx>" in reply:
        try:
            tx_str = reply.split("<tx>")[1].split("</tx>")[0]
            tx = json.loads(tx_str)
            tx["date"] = datetime.now().strftime("%d.%m.%Y")
            user["transactions"].append(tx)
            if tx["type"] == "expense":
                user["balance"] -= tx["amount"]
            else:
                user["balance"] += tx["amount"]
            reply = reply.split("<tx>")[0].strip()
        except:
            pass
    
    # Обрабатываем цели
    if "<goal>" in reply and "</goal>" in reply:
        try:
            goal_str = reply.split("<goal>")[1].split("</goal>")[0]
            goal = json.loads(goal_str)
            user["goals"].append(goal)
            reply = reply.split("<goal>")[0].strip()
        except:
            pass
    
    # Сохраняем историю
    user["history"].append({"role": "user", "content": user_message})
    user["history"].append({"role": "assistant", "content": reply})
    if len(user["history"]) > 20:
        user["history"] = user["history"][-20:]
    
    return reply

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    text = f"""👋 Привет, {user_name}!

Я **FinMind AI** — твой личный финансовый помощник.

Я умею:
💰 Считать твои доходы и расходы
🎯 Помогать копить на цели
📊 Анализировать куда уходят деньги
💡 Давать советы по финансам

**Просто пиши мне как другу:**
• "Получил зарплату 3 000 000 сум"
• "Потратил 150 000 на еду"
• "Хочу накопить на ноутбук 5 000 000"

Начнём? Расскажи о своих финансах! 🚀"""
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    # Считаем статистику
    total_income = sum(t["amount"] for t in user["transactions"] if t["type"] == "income")
    total_expense = sum(t["amount"] for t in user["transactions"] if t["type"] == "expense")
    
    # Категории расходов
    categories = {}
    for t in user["transactions"]:
        if t["type"] == "expense":
            cat = t.get("category", "другое")
            categories[cat] = categories.get(cat, 0) + t["amount"]
    
    cat_text = ""
    for cat, amount in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]:
        cat_text += f"  • {cat}: {amount:,} сум\n"
    
    goals_text = ""
    for g in user["goals"]:
        progress = int((g["saved"] / g["target"]) * 100) if g["target"] > 0 else 0
        bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
        goals_text += f"  🎯 {g['name']}: {bar} {progress}%\n"
    
    text = f"""📊 **Твоя статистика**

💵 **Баланс:** {user['balance']:,} сум
📈 **Доходы:** {total_income:,} сум
📉 **Расходы:** {total_expense:,} сум

**Топ расходов:**
{cat_text if cat_text else '  Пока нет данных'}

**Цели:**
{goals_text if goals_text else '  Целей нет — поставь первую!'}

Транзакций всего: {len(user['transactions'])}"""
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def tip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    prompt = f"Дай один конкретный финансовый совет для молодого человека в Узбекистане. Баланс пользователя: {user['balance']} сум. Очень кратко — 2-3 предложения максимум."
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    
    await update.message.reply_text(f"💡 **Совет дня:**\n\n{response.content[0].text}", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        reply = get_ai_response(user_id, user_message)
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Что-то пошло не так. Попробуй ещё раз!")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("tip", tip))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ FinMind AI бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
