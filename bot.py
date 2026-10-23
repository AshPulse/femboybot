import asyncio
import os
import logging
import traceback
import aiohttp
import discord
from discord.ext import commands

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("snap")

TOKEN = os.getenv("TOKEN", "IL_TUO_TOKEN")

WELCOME_CHANNEL_ID          = 1562890044455526551
TICKET_SUPPORT_CATEGORY_ID  = 1562900594367270963
TICKET_PURCHASE_CATEGORY_ID = 1562900617385480212
STAFF_ROLE_ID               = 1562900424233848852
LTC_ADDRESS                 = "LZnytAtTzjGqUeLWHpkvhkK2U8z5f5fov5"
PRICE_USD                   = 10

CHANNEL_FEATURES_ID         = 1562901227254185994
CHANNEL_TICKETS_ID          = 1562901115803144315

ALERT_EMOJI    = "<a:Alert:1562891464432943124>"
QUESTION_EMOJI = "<:question:1562891360850284595>"
WARN_EMOJI     = "<a:warnings:1562891301760802938>"
GUIDE_EMOJI    = "<:guide:1562891148928884789>"
MONEY_EMOJI    = "<:money:1562891076006584373>"
SHOP_EMOJI     = "<a:shopping:1562891221423104072>"
TICKET_EMOJI   = "<:ticket:1562891010999062739>"

WHITE  = 0xFFFFFF
YELLOW = 0xFACC15

# ── LTC ───────────────────────────────────────────────────────────────────────
async def _usd_to_ltc(usd: float):
    url = "https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                rate = float(data["litecoin"]["usd"])
                return round(usd / rate, 6) if rate > 0 else None
    except Exception:
        return None

# ── TICKET HELPERS ─────────────────────────────────────────────────────────────
def _find_user_ticket(guild: discord.Guild, user_id: int):
    for ch in guild.text_channels:
        if ch.category_id in {TICKET_SUPPORT_CATEGORY_ID, TICKET_PURCHASE_CATEGORY_ID}:
            if f"owner:{user_id}" in (ch.topic or ""):
                return ch
    return None

async def _create_ticket_channel(guild: discord.Guild, user: discord.Member, category_id: int, kind: str):
    category   = guild.get_channel(category_id)
    staff_role = guild.get_role(STAFF_ROLE_ID)
    if category is None:
        raise RuntimeError("Category not found. Check the category ID in the config.")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user:               discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    channel = await guild.create_text_channel(
        f"{kind}-{user.name}"[:95],
        category=category,
        overwrites=overwrites,
        topic=f"owner:{user.id}",
    )
    return channel

# ── TICKET CONTROL VIEW (Ping Staff + Close) ──────────────────────────────────
class TicketControlView(discord.ui.View):
    """Persistent — lives forever on every ticket message."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ping Staff", style=discord.ButtonStyle.secondary,
                        emoji=discord.PartialEmoji.from_str(ALERT_EMOJI),
                        custom_id="snap:ping_staff")
    async def ping_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        button.label = "Staff Pinged"
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass
        await interaction.channel.send(
            content=f"<@&{STAFF_ROLE_ID}>",
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger,
                        emoji=discord.PartialEmoji.from_str(WARN_EMOJI),
                        custom_id="snap:close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            description=f"{WARN_EMOJI} **Ticket closed.**\nThis channel will be deleted in 5 seconds.",
            color=WHITE,
        )
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

# ── PANEL VIEW (Purchase + Support) ───────────────────────────────────────────
class TicketPanelView(discord.ui.View):
    """Persistent — lives forever on the panel message."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Purchase", style=discord.ButtonStyle.success,
                        emoji=discord.PartialEmoji.from_str(MONEY_EMOJI),
                        custom_id="snap:purchase")
    async def purchase(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏳ Opening your ticket...", ephemeral=True)
        guild, user = interaction.guild, interaction.user

        existing = _find_user_ticket(guild, user.id)
        if existing:
            await interaction.edit_original_response(content=f"You already have an open ticket: {existing.mention}")
            return

        try:
            channel = await _create_ticket_channel(guild, user, TICKET_PURCHASE_CATEGORY_ID, "purchase")
        except Exception as e:
            log.error(f"purchase ticket creation failed: {e}\n{traceback.format_exc()}")
            await interaction.edit_original_response(content=f"❌ {e}")
            return

        ltc     = await _usd_to_ltc(PRICE_USD)
        ltc_str = f"{ltc} LTC" if ltc else "Ask staff (rate unavailable)"
        embed = discord.Embed(
            title=f"{SHOP_EMOJI} Purchase — Premium Access",
            description=(
                f"Send the exact amount to the address below to complete your purchase.\n\n"
                f"{WARN_EMOJI} **Do NOT pay any staff member. Only use this address.**"
            ),
            color=YELLOW,
        )
        embed.add_field(name="Plan", value=f"Premium Access — ${PRICE_USD} USD", inline=False)
        embed.add_field(name="LTC Amount", value=f"```{ltc_str}```", inline=False)
        embed.add_field(name="Payment Address", value=f"```{LTC_ADDRESS}```", inline=False)
        embed.set_footer(text="Once your payment is confirmed, staff will grant you access.")
        await channel.send(content=f"{user.mention}", embed=embed, view=TicketControlView())
        await interaction.edit_original_response(content=f"✅ Ticket opened: {channel.mention}")

    @discord.ui.button(label="Support", style=discord.ButtonStyle.secondary,
                        emoji=discord.PartialEmoji.from_str(GUIDE_EMOJI),
                        custom_id="snap:support")
    async def support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏳ Opening your ticket...", ephemeral=True)
        guild, user = interaction.guild, interaction.user

        existing = _find_user_ticket(guild, user.id)
        if existing:
            await interaction.edit_original_response(content=f"You already have an open ticket: {existing.mention}")
            return

        try:
            channel = await _create_ticket_channel(guild, user, TICKET_SUPPORT_CATEGORY_ID, "support")
        except Exception as e:
            log.error(f"support ticket creation failed: {e}\n{traceback.format_exc()}")
            await interaction.edit_original_response(content=f"❌ {e}")
            return

        embed = discord.Embed(
            title=f"{GUIDE_EMOJI} Support Ticket",
            description=(
                "Welcome! A staff member will be with you shortly.\n\n"
                "Describe your issue below, then press **Ping Staff** when ready."
            ),
            color=WHITE,
        )
        await channel.send(content=f"{user.mention}", embed=embed, view=TicketControlView())
        await interaction.edit_original_response(content=f"✅ Ticket opened: {channel.mention}")

# ── WELCOME ───────────────────────────────────────────────────────────────────
def _welcome_embed(member: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        description=(
            f"## {ALERT_EMOJI} Welcome, {member.mention}!\n"
            f"Glad to have you in **{member.guild.name}**. Check out the channels below to get started."
        ),
        color=WHITE,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Member #{member.guild.member_count}")
    return embed

def _welcome_view(guild_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label="Premium Features", style=discord.ButtonStyle.link,
        emoji=discord.PartialEmoji.from_str(MONEY_EMOJI),
        url=f"https://discord.com/channels/{guild_id}/{CHANNEL_FEATURES_ID}",
    ))
    view.add_item(discord.ui.Button(
        label="Open a Ticket", style=discord.ButtonStyle.link,
        emoji=discord.PartialEmoji.from_str(TICKET_EMOJI),
        url=f"https://discord.com/channels/{guild_id}/{CHANNEL_TICKETS_ID}",
    ))
    return view

def _ticket_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title=f"{TICKET_EMOJI} Support Tickets",
        description=(
            "Need help or want to get access? Open a ticket and our team will assist you.\n\n"
            f"{MONEY_EMOJI} **Purchase** — Get Premium Access for **$10** via Litecoin.\n"
            f"{GUIDE_EMOJI} **Support** — Have a question or issue? We're here to help."
        ),
        color=WHITE,
    )
    return embed

# ── BOT ───────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    for g in bot.guilds:
        bot.tree.copy_global_to(guild=g)
        await bot.tree.sync(guild=g)
    log.info(f"Online as {bot.user}")

@bot.event
async def on_member_join(member: discord.Member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch is None:
        return
    await ch.send(embed=_welcome_embed(member), view=_welcome_view(member.guild.id))

@bot.command(name="ticket")
async def ticket_panel_cmd(ctx):
    if not ctx.author.guild_permissions.administrator:
        return
    try:
        async for m in ctx.channel.history(limit=20):
            if m.author == bot.user:
                await m.delete()
    except Exception:
        pass
    await ctx.channel.send(embed=_ticket_panel_embed(), view=TicketPanelView())
    try:
        await ctx.message.delete()
    except Exception:
        pass

@bot.event
async def on_error(event, *args, **kwargs):
    log.error(f"Error in {event}:\n{traceback.format_exc()}")

bot.run(TOKEN)
