from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Buy Number", callback_data="menu_buy")],
        [InlineKeyboardButton(text="📱 My Numbers", callback_data="menu_numbers")],
        [InlineKeyboardButton(text="💳 Buy SMS Credits", callback_data="menu_credits")],
        [InlineKeyboardButton(text="📜 SMS History", callback_data="menu_history")],
        [InlineKeyboardButton(text="🤝 Refer & Earn", callback_data="menu_referral")],
        [InlineKeyboardButton(text="🆘 Support", callback_data="menu_support")],
    ])


def country_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 United States", callback_data="country_us")],
        [InlineKeyboardButton(text="🇨🇦 Canada", callback_data="country_ca")],
        [InlineKeyboardButton(text="🇬🇧 United Kingdom", callback_data="country_uk")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_back")],
    ])


def duration_menu(country: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Month — ₦3,000", callback_data=f"dur_{country}_1")],
        [InlineKeyboardButton(text="3 Months — ₦8,000", callback_data=f"dur_{country}_3")],
        [InlineKeyboardButton(text="6 Months — ₦14,000", callback_data=f"dur_{country}_6")],
        [InlineKeyboardButton(text="1 Year — ₦25,000", callback_data=f"dur_{country}_12")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_buy")],
    ])


def credit_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Starter: 20 SMS — ₦2,000", callback_data="cred_20_2000")],
        [InlineKeyboardButton(text="Standard: 50 SMS — ₦4,500", callback_data="cred_50_4500")],
        [InlineKeyboardButton(text="Premium: 100 SMS — ₦8,000", callback_data="cred_100_8000")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_back")],
    ])


def confirm_payment_menu(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Pay Now", callback_data=f"pay_{callback_data}")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_back")],
    ])


def number_actions_menu(number_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Renew", callback_data=f"renew_{number_id}")],
        [InlineKeyboardButton(text="📜 SMS History", callback_data=f"hist_{number_id}")],
        [InlineKeyboardButton(text="💳 Top Up Credits", callback_data=f"topup_{number_id}")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_numbers")],
    ])


def support_menu(admin_bot_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Contact Support", url=admin_bot_link)],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_back")],
    ])


def back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Main Menu", callback_data="menu_back")],
    ])
