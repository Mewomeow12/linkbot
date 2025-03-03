from pymongo import MongoClient
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import logging
from BotToken import Token

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# MongoDB Connection
client = MongoClient('mongodb+srv://noobwalker7594:8GB5h8bt4Ji4IkEG@linkbot.w05pt.mongodb.net/?retryWrites=true&w=majority&appName=Linkbot')
db = client['Link_Bot']
users_collection = db['users']
links_collection = db['links']
pending_collection = db['pending_links']

ADMIN_ID = 5667016949  # Change this to your Telegram user ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command - registers the user and greets them."""
    user = update.message.from_user
    users_collection.update_one(
        {"user_id": user.id}, 
        {"$setOnInsert": {"user_id": user.id, "username": user.username, "first_name": user.first_name}}, 
        upsert=True
    )
    
    await update.message.reply_text("Hello! Use /add to save a link.")

async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiate adding a link process."""
    context.user_data["step"] = "keyword"
    context.user_data["keywords"] = []  # Store multiple keywords
    await update.message.reply_text("Send keywords one by one. When done, send the link.")

async def receive_keyword_or_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles receiving either a keyword or a link."""
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    # Check if input is a link
    if text.startswith("http://") or text.startswith("https://"):
        if context.user_data.get("step") == "keyword":
            if not context.user_data.get("keywords"):
                await update.message.reply_text("You must send at least one keyword before sending a link.")
                return

            # Store the link and submit for approval
            keywords = context.user_data["keywords"]

            pending_collection.update_one(
                {"user_id": user_id, "link": text},
                {"$set": {"user_id": user_id, "link": text, "status": "pending"},
                 "$addToSet": {"keywords": {"$each": keywords}}},
                upsert=True
            )

            keyboard = [[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("❌ Decline", callback_data=f"decline_{user_id}")
            ]]

            # Format as a table
            formatted_message = (
                "📝 **New Link Submission**\n"
                "----------------------------------\n"
                f"👤 **User ID**: `{user_id}`\n"
                f"🔗 **Link**: {text}\n"
                f"📝 **Keywords**: {', '.join(keywords)}\n"
                "----------------------------------"
            )

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=formatted_message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

            await update.message.reply_text("Your link has been submitted for approval.")
            context.user_data.clear()
        else:
            await update.message.reply_text("Use /add to start the process.")

    # If it's a keyword, retrieve all matching links
    else:
        if context.user_data.get("step") == "keyword":
            context.user_data["keywords"].append(text)
            await update.message.reply_text(f"Keyword '{text}' added. Send more or send the link.")
        else:
            # Find all matching links
            matching_links = links_collection.find({"keywords": text})
            links_list = [f"{idx+1}. {doc['link']}" for idx, doc in enumerate(matching_links)]

            if links_list:
                response_message = f"🔍 **Links for '{text}':**\n"
                for link in links_list:
                    if len(response_message) + len(link) > 4000:
                        await update.message.reply_text(response_message, disable_web_page_preview=True)
                        response_message = ""  # Reset message
                    response_message += link + "\n"

                if response_message:
                    await update.message.reply_text(response_message, disable_web_page_preview=True)
            else:
                await update.message.reply_text("No links found for this keyword.")

async def my_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays all links added by the user."""
    user_id = update.message.from_user.id
    user_links = links_collection.find({"user_id": user_id})
    links_list = [f"{idx+1}. {doc['link']}" for idx, doc in enumerate(user_links)]

    if links_list:
        response_message = "📌 **Your Links:**\n"
        for link in links_list:
            if len(response_message) + len(link) > 4000:
                await update.message.reply_text(response_message, disable_web_page_preview=True)
                response_message = ""  # Reset message
            response_message += link + "\n"

        if response_message:
            await update.message.reply_text(response_message, disable_web_page_preview=True)
    else:
        await update.message.reply_text("You have not added any links yet.")

async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles approval and rejection of submitted links."""
    query = update.callback_query
    action, user_id = query.data.split("_")
    user_id = int(user_id)

    pending_link = pending_collection.find_one({"user_id": user_id})

    if not pending_link:
        await query.answer("This request no longer exists.")
        return

    if action == "approve":
        links_collection.update_one(
            {"link": pending_link["link"]},
            {"$set": {"user_id": user_id, "link": pending_link["link"]},
             "$addToSet": {"keywords": {"$each": pending_link["keywords"]}}},
            upsert=True
        )

        await context.bot.send_message(user_id, f"✅ Your link '{pending_link['link']}' has been approved!")
        pending_collection.delete_one({"user_id": user_id})
    elif action == "decline":
        await context.bot.send_message(user_id, f"❌ Your link '{pending_link['link']}' was declined.")
        pending_collection.delete_one({"user_id": user_id})
    
    await query.answer()
    await query.edit_message_text("✅ Action processed successfully.")

def main():
    """Main function to start the bot."""
    application = ApplicationBuilder().token(Token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_link))
    application.add_handler(CommandHandler("mylinks", my_links))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_keyword_or_link))
    application.add_handler(CallbackQueryHandler(handle_approval))

    application.run_polling()

if __name__ == "__main__":
    main()
