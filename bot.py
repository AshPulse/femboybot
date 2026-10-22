import asyncio
import os
import aiohttp
import discord
from discord.ext import commands

# ── TOKEN ─────────────────────────────────────────────────────────────────────
TOKEN = os.getenv("TOKEN", "IL_TUO_TOKEN")

# ── CONFIG ────────────────────────────────────────────────────────────────────
WELCOME_CHANNEL_ID          = 1562890044455526551
TICKET_SUPPORT_CATEGORY_ID  = 1562900594367270963
TICKET_PURCHASE_CATEGORY_ID = 1562900617385480212
STAFF_ROLE_ID               = 1562900424233848852
LTC_ADDRESS                 = "LZnytAtTzjGqUeLWHpkvhkK2U8z5f5fov5"
PRICE_USD                   = 10

# ── EMOJI ─────────────────────────────────────────────────────────────────────
ALERT_EMOJI    = "<a:Alert:1562891464432943124>"
QUESTION_EMOJI = "<:question:1562891360850284595>"
WARN_EMOJI     = "<a:warnings:1562891301760802938>"
GUIDE_EMOJI    = "<:guide:1562891148928884789>"
MONEY_EMOJI    = "<:money:1562891076006584373>"
SHOP_EMOJI     = "<a:shopping:1562891221423104072>"
TICKET_EMOJI   = "<:ticket:1562891010999062739>"

# ── LTC HELPER ────────────────────────────────────────────────────────────────
async def _usd_to_ltc(usd: float):
    url = "https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                rate = float(data["litecoin"]["usd"])
                return round(usd / rate, 6) if rate > 0 else None
    except Exception:
        return None

# ── TICKET HELPERS ────────────────────────────────────────────────────────────
async def _find_user_ticket(guild, user_id: int):
    for ch in guild.text_channels:
        if ch.category_id in {TICKET_SUPPORT_CATEGORY_ID, TICKET_PURCHASE_CATEGORY_ID}:
            if f"owner:{user_id}" in (ch.topic or ""):
                return ch
    return None

async def _open_ticket(interaction: discord.Interaction, category_id: int, kind: str):
    guild = interaction.guild
    user  = interaction.user

    existing = await _find_user_ticket(guild, user.id)
    if existing:
        await interaction.response.send_message(
            f"You already have an open ticket: {existing.mention}", ephemeral=True
        )
        return None

    category   = guild.get_channel(category_id)
    staff_role = guild.get_role(STAFF_ROLE_ID)

    if category is None:
        await interaction.response.send_message("❌ Ticket category not found.", ephemeral=True)
        return None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user:               discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    try:
        channel = await guild.create_text_channel(
            f"{kind}-{user.name}",
            category=category,
            overwrites=overwrites,
            topic=f"owner:{user.id}",
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
        return None

    try:
        await channel.send(
            content=f"<@&{STAFF_ROLE_ID}> {user.mention}",
            allowed_mentions=discord.AllowedMentions(roles=True, users=True),
        )
    except Exception:
        pass

    return channel

# ── VIEWS ─────────────────────────────────────────────────────────────────────

class CloseTicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            emoji=discord.PartialEmoji.from_str(WARN_EMOJI),
            custom_id="snap:close_ticket",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Closing in 5 seconds...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass


class SupportTicketView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        body = (
            f"# {GUIDE_EMOJI} Support\n"
            f"Welcome! Describe your issue and a staff member will assist you shortly.\n\n"
            f"Press **Close Ticket** once your issue has been resolved."
        )
        c = discord.ui.Container(accent_colour=0x4A9EFF)
        c.add_item(discord.ui.TextDisplay(body))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(CloseTicketButton()))
        self.add_item(c)


class PurchaseTicketView(discord.ui.LayoutView):
    def __init__(self, ltc_str: str):
        super().__init__(timeout=None)
        body = (
            f"# {SHOP_EMOJI} Purchase — Premium Access\n"
            f"Send the exact LTC amount to the address below to complete your purchase.\n\n"
            f"{WARN_EMOJI} **Do NOT pay any staff member directly. Only use this address.**\n\n"
            f"**Plan**\n```Premium Access — ${PRICE_USD} USD```\n"
            f"**LTC Amount**\n```{ltc_str}```\n"
            f"**Payment Address**\n```{LTC_ADDRESS}```\n\n"
            f"Once payment is confirmed, staff will grant you access."
        )
        c = discord.ui.Container(accent_colour=0xFACC15)
        c.add_item(discord.ui.TextDisplay(body))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(CloseTicketButton()))
        self.add_item(c)


class PurchaseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Purchase",
            style=discord.ButtonStyle.success,
            emoji=discord.PartialEmoji.from_str(MONEY_EMOJI),
            custom_id="snap:purchase",
        )

    async def callback(self, interaction: discord.Interaction):
        channel = await _open_ticket(interaction, TICKET_PURCHASE_CATEGORY_ID, "purchase")
        if channel is None:
            return
        ltc     = await _usd_to_ltc(PRICE_USD)
        ltc_str = f"{ltc} LTC" if ltc else "Ask staff (rate unavailable)"
        await channel.send(view=PurchaseTicketView(ltc_str))
        await interaction.followup.send(
            f"✅ Purchase ticket opened: {channel.mention}", ephemeral=True
        )


class SupportButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Support",
            style=discord.ButtonStyle.primary,
            emoji=discord.PartialEmoji.from_str(GUIDE_EMOJI),
            custom_id="snap:support",
        )

    async def callback(self, interaction: discord.Interaction):
        channel = await _open_ticket(interaction, TICKET_SUPPORT_CATEGORY_ID, "support")
        if channel is None:
            return
        await channel.send(view=SupportTicketView())
        await interaction.followup.send(
            f"✅ Support ticket opened: {channel.mention}", ephemeral=True
        )


class TicketPanelView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        body = (
            f"# {TICKET_EMOJI} Tickets\n"
            f"Need help or want to get access? Open a ticket below.\n\n"
            f"{MONEY_EMOJI} **Premium Access** — $10 one-time payment via Litecoin (LTC).\n"
            f"Get full access to all server features.\n\n"
            f"{GUIDE_EMOJI} **Support** — Open a ticket if you have any questions or issues."
        )
        c = discord.ui.Container(accent_colour=0x4A9EFF)
        c.add_item(discord.ui.TextDisplay(body))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(PurchaseButton(), SupportButton()))
        self.add_item(c)

# ── BOT ───────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    bot.add_view(TicketPanelView())
    bot.add_view(SupportTicketView())
    for g in bot.guilds:
        bot.tree.copy_global_to(guild=g)
        await bot.tree.sync(guild=g)
    print(f"Online as {bot.user}")

@bot.event
async def on_member_join(member: discord.Member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch is None:
        return
    embed = discord.Embed(
        description=(
            f"# {ALERT_EMOJI} Welcome, {member.mention}!\n"
            f"Glad to have you here. Read the rules and enjoy your stay.\n\n"
            f"{QUESTION_EMOJI} Need help? Open a ticket in the support channel."
        ),
        color=0x4A9EFF,
    )
    embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Member #{member.guild.member_count}")
    await ch.send(embed=embed)

@bot.command(name="ticket")
async def ticket_panel_cmd(ctx):
    """!ticket — posta il panel nel canale corrente (solo admin)."""
    if not ctx.author.guild_permissions.administrator:
        return
    try:
        async for m in ctx.channel.history(limit=20):
            if m.author == bot.user:
                await m.delete()
    except Exception:
        pass
    await ctx.channel.send(view=TicketPanelView())
    try:
        await ctx.message.delete()
    except Exception:
        pass

bot.run(TOKEN)
