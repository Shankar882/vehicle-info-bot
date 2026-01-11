import requests
from bs4 import BeautifulSoup
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
import time
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# ===============================================
# CONFIGURATION
# ===============================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0"
}

# Telegram Bot Configuration
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Change this
ADMIN_CHAT_ID = "YOUR_CHAT_ID_HERE"    # Change this

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===============================================
# MULTI-SOURCE VEHICLE INFO SCRAPER
# ===============================================
def get_vehicle_details(rc_number: str) -> dict:
    """Fetch vehicle details from multiple sources."""
    rc = rc_number.strip().upper()
    
    # Try multiple sources
    sources = [
        fetch_from_rc_info,
        fetch_from_vahan_parivahan,
        fetch_from_car_info
    ]
    
    for source_func in sources:
        try:
            data = source_func(rc)
            if data and not data.get("error"):
                logger.info(f"Data fetched successfully from {source_func.__name__}")
                return data
        except Exception as e:
            logger.warning(f"Failed from {source_func.__name__}: {str(e)}")
            continue
    
    return {"error": "Unable to fetch vehicle details from any source. Please try again later."}

def fetch_from_rc_info(rc: str) -> dict:
    """Fetch from rc-info website."""
    try:
        url = f"https://www.rc-info.com/{rc}"
        response = requests.get(url, headers=HEADERS, timeout=15)
        
        if response.status_code != 200:
            return {"error": f"Website returned status {response.status_code}"}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract information based on common patterns
        data = {
            "registration_number": rc,
            "status": "success",
            "source": "rc-info.com"
        }
        
        # Look for common vehicle info patterns
        details = {}
        
        # Try to find tables or divs with vehicle info
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) == 2:
                    key = cols[0].text.strip().lower().replace(' ', '_')
                    value = cols[1].text.strip()
                    if key and value:
                        details[key] = value
        
        # Also look for div-based layouts
        info_divs = soup.find_all(['div', 'section'], class_=re.compile(r'info|detail|spec', re.I))
        for div in info_divs:
            spans = div.find_all(['span', 'strong', 'b'])
            for i in range(0, len(spans)-1, 2):
                key = spans[i].text.strip().lower().replace(' ', '_').replace(':', '')
                value = spans[i+1].text.strip() if i+1 < len(spans) else ''
                if key and value:
                    details[key] = value
        
        # Map extracted data to our structure
        data.update(map_details_to_structure(details))
        return data
        
    except Exception as e:
        return {"error": f"rc-info error: {str(e)}"}

def fetch_from_vahan_parivahan(rc: str) -> dict:
    """Try parivahan website."""
    try:
        url = "https://vahan.parivahan.gov.in/vahan4dashboard/"
        search_url = f"https://www.google.com/search?q={rc}+vehicle+details+parivahan"
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        data = {
            "registration_number": rc,
            "status": "success",
            "source": "parivahan-search"
        }
        
        snippets = soup.find_all(['div', 'span'], class_=re.compile(r'snippet|result', re.I))
        details = {}
        
        for snippet in snippets:
            text = snippet.text.lower()
            if any(keyword in text for keyword in ['owner', 'model', 'chassis', 'engine', 'fuel', 'insurance']):
                lines = snippet.text.split('\n')
                for line in lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower().replace(' ', '_')
                        value = value.strip()
                        details[key] = value
        
        data.update(map_details_to_structure(details))
        
        if len(details) > 0:
            return data
        else:
            return {"error": "No details found in search results"}
            
    except Exception as e:
        return {"error": f"parivahan error: {str(e)}"}

def fetch_from_car_info(rc: str) -> dict:
    """Try general car info websites."""
    try:
        queries = [
            f"{rc} vehicle owner details",
            f"{rc} rc information",
            f"{rc} car details India"
        ]
        
        all_details = {}
        
        for query in queries:
            try:
                search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
                response = requests.get(search_url, headers=HEADERS, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                knowledge_panel = soup.find('div', class_=re.compile(r'knowledge|fact', re.I))
                if knowledge_panel:
                    items = knowledge_panel.find_all(['div', 'tr'])
                    for item in items:
                        text = item.text.lower()
                        if ':' in text:
                            parts = text.split(':', 1)
                            if len(parts) == 2:
                                key = parts[0].strip().replace(' ', '_')
                                value = parts[1].strip()
                                all_details[key] = value
            except:
                continue
        
        if all_details:
            data = {
                "registration_number": rc,
                "status": "success",
                "source": "web-search",
                "basic_info": {
                    "registration_number": rc
                }
            }
            
            mapping = {
                'owner': 'owner_name',
                'model': 'model_name',
                'make': 'maker',
                'fuel': 'fuel_type',
                'chassis': 'chassis_number',
                'engine': 'engine_number',
                'registration_date': 'registration_date'
            }
            
            for key, value in all_details.items():
                for search_key, map_key in mapping.items():
                    if search_key in key:
                        if 'basic_info' not in data:
                            data['basic_info'] = {}
                        data['basic_info'][map_key] = value
            
            return data
        
        return {"error": "No information found"}
        
    except Exception as e:
        return {"error": f"car info error: {str(e)}"}

def map_details_to_structure(details: dict) -> dict:
    """Map extracted details to standard structure."""
    result = {
        "basic_info": {},
        "vehicle_details": {},
        "insurance": {},
        "validity": {}
    }
    
    mappings = {
        'owner': ('basic_info', 'owner_name'),
        'name': ('basic_info', 'owner_name'),
        'model': ('basic_info', 'model_name'),
        'address': ('basic_info', 'address'),
        'city': ('basic_info', 'city'),
        'state': ('basic_info', 'state'),
        'phone': ('basic_info', 'phone'),
        'make': ('vehicle_details', 'maker'),
        'vehicle_class': ('vehicle_details', 'vehicle_class'),
        'fuel_type': ('vehicle_details', 'fuel_type'),
        'cc': ('vehicle_details', 'cubic_capacity'),
        'seating': ('vehicle_details', 'seating_capacity'),
        'chassis': ('vehicle_details', 'chassis_number'),
        'engine': ('vehicle_details', 'engine_number'),
        'insurance': ('insurance', 'company'),
        'policy': ('insurance', 'policy_number'),
        'insurance_valid': ('insurance', 'valid_upto'),
        'registration_date': ('validity', 'registration_date'),
        'fitness': ('validity', 'fitness_upto'),
        'tax': ('validity', 'tax_upto'),
        'puc': ('validity', 'puc_upto')
    }
    
    for detail_key, detail_value in details.items():
        detail_key_lower = detail_key.lower()
        for map_key, (category, field) in mappings.items():
            if map_key in detail_key_lower:
                result[category][field] = detail_value
                break
    
    return result

# ===============================================
# TELEGRAM BOT FUNCTIONS
# ===============================================
def format_vehicle_details_for_telegram(data):
    """Format vehicle details for Telegram message."""
    if data.get("error"):
        return f"❌ *Error:* {data['error']}\n\nPlease try again with a different RC number."
    
    message = f"🚗 *Vehicle Details for {data['registration_number']}*\n"
    message += f"📊 *Source:* {data.get('source', 'Multiple Sources')}\n\n"
    
    # Basic Information
    if data.get("basic_info"):
        bi = data["basic_info"]
        message += "📋 *BASIC INFORMATION*\n"
        message += "┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
        
        if bi.get("owner_name"):
            message += f"• 👤 *Owner:* {bi['owner_name']}\n"
        if bi.get("model_name"):
            message += f"• 🚗 *Model:* {bi['model_name']}\n"
        if bi.get("address"):
            message += f"• 📍 *Address:* {bi['address'][:50]}...\n"
        if bi.get("city"):
            message += f"• 🏙️ *City:* {bi['city']}\n"
        if bi.get("state"):
            message += f"• 🏛️ *State:* {bi['state']}\n"
        message += "\n"
    
    # Vehicle Details
    if data.get("vehicle_details"):
        vd = data["vehicle_details"]
        if any(vd.values()):
            message += "🚙 *VEHICLE SPECIFICATIONS*\n"
            message += "┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
            
            if vd.get("maker"):
                message += f"• 🏭 *Maker:* {vd['maker']}\n"
            if vd.get("vehicle_class"):
                message += f"• 🏷️ *Class:* {vd['vehicle_class']}\n"
            if vd.get("fuel_type"):
                message += f"• ⛽ *Fuel:* {vd['fuel_type']}\n"
            if vd.get("cubic_capacity"):
                message += f"• 🔧 *CC:* {vd['cubic_capacity']}\n"
            if vd.get("seating_capacity"):
                message += f"• 💺 *Seats:* {vd['seating_capacity']}\n"
            if vd.get("chassis_number"):
                message += f"• 🔢 *Chassis:* {vd['chassis_number'][:15]}...\n"
            if vd.get("engine_number"):
                message += f"• ⚙️ *Engine:* {vd['engine_number'][:15]}...\n"
            message += "\n"
    
    # Insurance Details
    if data.get("insurance"):
        ins = data["insurance"]
        if any(ins.values()):
            message += "🛡️ *INSURANCE DETAILS*\n"
            message += "┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
            
            if ins.get("company"):
                message += f"• 🏢 *Company:* {ins['company']}\n"
            if ins.get("policy_number"):
                message += f"• 📄 *Policy:* {ins['policy_number']}\n"
            if ins.get("valid_upto"):
                message += f"• 📅 *Valid Until:* {ins['valid_upto']}\n"
            if ins.get("expiry_date"):
                message += f"• ⏳ *Expires:* {ins['expiry_date']}\n"
            message += "\n"
    
    # Validity Information
    if data.get("validity"):
        val = data["validity"]
        if any(val.values()):
            message += "📅 *VALIDITY INFORMATION*\n"
            message += "┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
            
            if val.get("registration_date"):
                message += f"• 📆 *Reg. Date:* {val['registration_date']}\n"
            if val.get("fitness_upto"):
                message += f"• ✅ *Fitness Until:* {val['fitness_upto']}\n"
            if val.get("tax_upto"):
                message += f"• 💵 *Tax Paid Until:* {val['tax_upto']}\n"
            if val.get("puc_upto"):
                message += f"• 🔍 *PUC Until:* {val['puc_upto']}\n"
            message += "\n"
    
    # Add footer
    message += "━━━━━━━━━━━━━━━━━━━━\n"
    message += f"⏰ *Last Updated:* {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    message += "ℹ️ *Note:* Information from public sources"
    
    return message

# ===============================================
# TELEGRAM BOT HANDLERS
# ===============================================
async def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    
    welcome_message = (
        f"👋 *Welcome {user.first_name}!*\n\n"
        "🚗 *Vehicle Information Bot*\n\n"
        "I can help you find vehicle details using RC number.\n\n"
        "*How to use:*\n"
        "Simply send me a vehicle RC number\n"
        "*Example:* `DL01AB1234` or `MH02CD5678`\n\n"
        "*Features:*\n"
        "• Owner Information\n"
        "• Vehicle Specifications\n"
        "• Insurance Details\n"
        "• Validity Information\n\n"
        "*Commands:*\n"
        "/start - Start the bot\n"
        "/help - Show help guide\n"
        "/about - About this bot\n\n"
        "⚠️ *Disclaimer:* Information is from public sources only."
    )
    
    keyboard = [
        [InlineKeyboardButton("🚗 Search Vehicle", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("📖 Help", callback_data='help'),
         InlineKeyboardButton("ℹ️ About", callback_data='about')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message, 
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    # Notify admin
    admin_msg = f"🆕 New user:\n👤 {user.full_name}\n🆔 {user.id}\n📱 @{user.username}"
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg)
    except:
        pass

async def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "📖 *Help Guide*\n\n"
        "*How to search:*\n"
        "1. Send RC number directly\n"
        "2. Format: XX##XX####\n"
        "   - First 2: State (DL, MH, KA, etc.)\n"
        "   - Next 2: RTO code\n"
        "   - Next 2: Series\n"
        "   - Last 4: Number\n\n"
        "*Examples:*\n"
        "• `DL01AB1234`\n"
        "• `MH02CD5678`\n"
        "• `KA03EF9012`\n\n"
        "*Need help?* Try different RC formats.\n\n"
        "*Note:* Not all RC numbers may return data."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def about_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /about is issued."""
    about_text = (
        "ℹ️ *About This Bot*\n\n"
        "*Vehicle Information Bot*\n"
        "Version: 3.0\n\n"
        "*Description:*\n"
        "Fetches vehicle details from multiple public sources using RC number.\n\n"
        "*Technology:*\n"
        "• Python\n"
        "• BeautifulSoup\n"
        "• Multiple Data Sources\n\n"
        "*Features:*\n"
        "• Multi-source data fetching\n"
        "• Fast response\n"
        "• Clean formatting\n\n"
        "👨‍💻 *For support:* Contact admin"
    )
    await update.message.reply_text(about_text, parse_mode='Markdown')

async def handle_rc_number(update: Update, context: CallbackContext) -> None:
    """Handle RC number input from user."""
    rc_number = update.message.text.strip().upper()
    
    # Basic validation
    if len(rc_number) < 5:
        await update.message.reply_text(
            "❌ *Invalid RC Number!*\n\n"
            "RC number should be at least 5 characters.\n"
            "*Example:* DL01AB1234\n\n"
            "Please try again.",
            parse_mode='Markdown'
        )
        return
    
    # Show searching message
    search_msg = await update.message.reply_text(
        f"🔍 *Searching for {rc_number}...*\n"
        "Checking multiple sources...",
        parse_mode='Markdown'
    )
    
    try:
        # Fetch vehicle details
        data = get_vehicle_details(rc_number)
        
        if data.get("error"):
            await search_msg.edit_text(
                f"❌ *No Data Found*\n\n"
                f"*RC Number:* {rc_number}\n\n"
                f"*Reason:* {data['error']}\n\n"
                "*Possible reasons:*\n"
                "• RC number not in public database\n"
                "• Data source temporarily unavailable\n"
                "• Invalid RC format\n\n"
                "Please try:\n"
                "1. Verify RC number\n"
                "2. Try different RC\n"
                "3. Try again later",
                parse_mode='Markdown'
            )
            return
        
        # Format and send results
        formatted_message = format_vehicle_details_for_telegram(data)
        
        # Create buttons
        keyboard = [
            [InlineKeyboardButton("🔄 Search Another", callback_data='new_search')],
            [InlineKeyboardButton("📤 Share This", switch_inline_query=rc_number)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await search_msg.edit_text(
            formatted_message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Log success
        logger.info(f"Success: {rc_number} - {data.get('source', 'unknown')}")
        
    except Exception as e:
        logger.error(f"Error: {rc_number} - {str(e)}")
        await search_msg.edit_text(
            f"❌ *Processing Error*\n\n"
            f"Error occurred while processing.\n"
            f"Please try again in some time.\n\n"
            f"*Error:* {str(e)[:100]}",
            parse_mode='Markdown'
        )

async def button_callback(update: Update, context: CallbackContext) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'help':
        await help_command_callback(query)
    elif query.data == 'about':
        await about_command_callback(query)
    elif query.data == 'new_search':
        await query.edit_message_text(
            "🔄 *New Search*\n\n"
            "Send me a vehicle RC number.\n"
            "*Example:* `DL01AB1234`",
            parse_mode='Markdown'
        )

async def help_command_callback(query):
    """Help for callback."""
    await query.edit_message_text(
        "📖 Send RC number to get vehicle details.\n"
        "Format: XX##XX####\n\n"
        "Need help? Contact admin.",
        parse_mode='Markdown'
    )

async def about_command_callback(query):
    """About for callback."""
    await query.edit_message_text(
        "ℹ️ *Vehicle Info Bot*\n"
        "Fetch vehicle details using RC num
