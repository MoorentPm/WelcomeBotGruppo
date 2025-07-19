import os
import logging
import re
from datetime import datetime
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# --- CONFIGURAZIONE INIZIALE ---

# Carica le variabili d'ambiente dal file .env
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROUP_INVITE_LINK = os.getenv("GROUP_INVITE_LINK")
# --- MODIFICA: Usiamo l'ID del foglio invece del nome ---
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")


# Controlla che le configurazioni essenziali siano presenti
if not BOT_TOKEN or not GROUP_INVITE_LINK or not GOOGLE_SHEET_ID:
    raise ValueError("Errore: devi impostare TELEGRAM_BOT_TOKEN, GROUP_INVITE_LINK e GOOGLE_SHEET_ID nel tuo file .env")

# Configura il logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Definiamo gli stati della conversazione
GET_NAME, GET_EMAIL = range(2)


# --- FUNZIONI DI GESTIONE DATI ---

def save_to_google_sheet(user_info: dict):
    """
    Salva le informazioni dell'utente in un Google Foglio.
    """
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file"
        ]
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
        client = gspread.authorize(creds)

        # --- MODIFICA: Apriamo il foglio tramite il suo ID univoco ---
        sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1

        # Controlla se l'intestazione è già presente, altrimenti la aggiunge
        if not sheet.get('A1'):
            headers = ["Nome Cognome", "Email", "ID Telegram", "Data Registrazione"]
            sheet.append_row(headers)
            logger.info("Intestazione aggiunta al Google Foglio.")

        # Aggiunge una nuova riga con i dati dell'utente
        new_row = [
            user_info["name"],
            user_info["email"],
            user_info["user_id"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ]
        sheet.append_row(new_row)
        logger.info(f"Nuovo utente {user_info['name']} salvato su Google Fogli.")
        return True
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"ERRORE: Foglio Google con ID '{GOOGLE_SHEET_ID}' non trovato. Controlla che l'ID sia corretto e che il foglio sia stato condiviso con l'email dell'account di servizio.")
        return False
    except gspread.exceptions.APIError as e:
        logger.error(f"ERRORE API GOOGLE: {e}. Controlla che le API 'Google Drive' e 'Google Sheets' siano abilitate nel tuo progetto Cloud.")
        return False
    except Exception as e:
        logger.error(f"Errore generico durante il salvataggio su Google Fogli: {e}")
        return False

def debug_google_access():
    """
    Funzione di debug per verificare se l'account di servizio può aprire il foglio tramite ID.
    """
    logger.info("--- ESECUZIONE DEBUG ACCESSO GOOGLE (TRAMITE ID) ---")
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file"
        ]
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
        client = gspread.authorize(creds)

        logger.info(f"Tentativo di aprire il foglio con ID: {GOOGLE_SHEET_ID}")
        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        logger.info(f"✅ SUCCESSO! Il bot ha aperto correttamente il foglio chiamato: '{sheet.title}'")
        logger.info("--- FINE DEBUG ---")
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f">>> FALLIMENTO! Il bot non riesce a trovare il foglio con ID '{GOOGLE_SHEET_ID}'.")
        logger.error("Verifica che l'ID nel file .env sia corretto e che il foglio sia condiviso con l'email del bot.")
        logger.info("--- FINE DEBUG ---")
    except Exception as e:
        logger.error(f"DEBUG ERRORE: Si è verificato un errore imprevisto: {e}")


def is_valid_email(email: str) -> bool:
    """Controlla se una stringa è un indirizzo email valido."""
    regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(regex, email) is not None


# --- GESTORI DELLA CONVERSAZIONE TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Punto di ingresso del bot."""
    user = update.effective_user
    await update.message.reply_html(
        f"👋 Ciao {user.first_name} e benvenuto/a!\n\n"
        "Per accedere al nostro gruppo esclusivo, ho bisogno di qualche informazione.\n\n"
        "Per favore, inviami il tuo <b>Nome e Cognome</b>.",
    )
    return GET_NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Riceve il nome e chiede l'email."""
    context.user_data['name'] = update.message.text
    logger.info(f"Nome ricevuto da {update.effective_user.id}: {update.message.text}")
    await update.message.reply_html("Grazie! Ora, per favore, inviami il tuo <b>indirizzo email</b>.")
    return GET_EMAIL


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Riceve l'email, valida, salva e termina la conversazione."""
    user_email = update.message.text
    if not is_valid_email(user_email):
        await update.message.reply_text("⚠️ L'indirizzo email non sembra valido. Per favore, controlla e riprova.")
        return GET_EMAIL

    logger.info(f"Email ricevuta da {update.effective_user.id}: {user_email}")
    context.user_data['email'] = user_email

    user_info = {
        "name": context.user_data['name'],
        "email": context.user_data['email'],
        "user_id": update.effective_user.id,
    }

    # Salva i dati su Google Fogli
    if save_to_google_sheet(user_info):
        keyboard = [[InlineKeyboardButton("➡️ Clicca qui per entrare ⬅️", url=GROUP_INVITE_LINK)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_html(
            "✅ Ottimo! Registrazione completata.\n\n"
            "Clicca sul pulsante qui sotto per accedere al gruppo esclusivo. Ti aspettiamo!",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "❌ Si è verificato un problema tecnico durante la registrazione. "
            "Il nostro team è stato notificato. Per favore, riprova più tardi."
        )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Annulla la conversazione."""
    await update.message.reply_text("Operazione annullata. Se cambi idea, scrivimi /start.")
    context.user_data.clear()
    return ConversationHandler.END


# --- FUNZIONE PRINCIPALE DEL BOT ---

def main() -> None:
    """Avvia il bot."""
    debug_google_access()

    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    logger.info("Il bot è online e in attesa di utenti...")
    application.run_polling()


if __name__ == "__main__":
    main()
