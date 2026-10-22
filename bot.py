import asyncio
import aiohttp
import discord
from discord.ext import commands

# ── TOKEN ────────────────────────────────────────────────────────────────────
import os
TOKEN = os.getenv("TOKEN")

# ── CONFIG ────────────────────────────────────────────────────────────────────
TICKET_PANEL_CHANNEL_ID     = 1537932706506215434
TICKET_SUPPORT_CATEGORY_ID  = 1543648690231705790
TICKET_PURCHASE_CATEGORY_ID = 1543864452447866991
STAFF_ROLE_ID               = 1558233114269061200
LTC_ADDRESS                 = "LZnytAtTzjGqUeLWHpkvhkK2U8z5f5fov5"

TICKET_PLANS = [
    {"key": "12h",  "label": "12h",      "usd": 5},
    {"key": "24h",  "label": "24h",      "usd": 10},
    {"key": "48h",  "label": "48h",      "usd": 20},
    {"key": "life", "label": "Lifetime", "usd": 450},
]

# ── EMOJI (aggiornate con i tuoi ID) ─────────────────────────────────────────
ALERT_EMOJI   = "<a:Alert:1562891464432943124>"
QUESTION_EMOJI = "<:question:1562891360850284595>"
WARN_EMOJI    = "<a:warnings:1562891301760802938>"
GUIDE_EMOJI   = "<:guide:1562891148928884789>"
MONEY_EMOJI   = "<:money:1562891076006584373>"
SHOP_EMOJI    = "<a:shopping:1562891221423104072>"
TICKET_EMOJI  = "<:ticket:1562891010999062739>"
FREEZE_EMOJI  = "<:question:1562891360850284595>"  # usato per Close (cambia se hai un'emoji ban)

# ── HELPERS ───────────────────────────────────────────────────────────────────

def _plan_by_key(key: str):
    return next((p for p in TICKET_PLANS if p["key"] == key), None)

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
            f"Hai già un ticket aperto: {existing.mention}", ephemeral=True
        )
        return None

    category   = guild.get_channel(category_id)
    staff_role = guild.get_role(STAFF_ROLE_ID)

    if category is None:
        await interaction.response.send_message("❌ Categoria ticket non trovata.", ephemeral=True)
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
        await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)
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
            label="Close",
            style=discord.ButtonStyle.danger,
            emoji=discord.PartialEmoji.from_str(FREEZE_EMOJI),
            custom_id="snapplus:close_ticket",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Chiusura in 5 secondi...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Ticket chiuso")
        except Exception:
            pass


class SupportTicketView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        body = (
            f"# {TICKET_EMOJI} Support Ticket\n"
            f"Grazie per aver aperto un ticket. Descrivi il problema "
            f"e lo staff ti risponderà a breve.\n\n"
            f"Premi **Close** quando hai finito."
        )
        c = discord.ui.Container(accent_colour=0x4A9EFF)
        c.add_item(discord.ui.TextDisplay(body))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(CloseTicketButton()))
        self.add_item(c)


class InvoiceView(discord.ui.LayoutView):
    def __init__(self, plan_label: str, usd: int, ltc_str: str):
        super().__init__(timeout=None)
        body = (
            f"# {SHOP_EMOJI} Fattura di Pagamento\n"
            f"Invia l'importo in Litecoin all'indirizzo qui sotto.\n\n"
            f"{WARN_EMOJI} **NON PAGARE LO STAFF — solo questo indirizzo LTC.**\n\n"
            f"**📦 Piano**\n```{plan_label} (${usd} USD)```\n"
            f"**🪙 Importo LTC**\n```{ltc_str}```\n"
            f"**🏦 Indirizzo**\n```{LTC_ADDRESS}```"
        )
        c = discord.ui.Container(accent_colour=0x4A9EFF)
        c.add_item(discord.ui.TextDisplay(body))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(CloseTicketButton()))
        self.add_item(c)


class PlanSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=f"{p['label']}  |  ${p['usd']}",
                value=p["key"],
                emoji=discord.PartialEmoji.from_str(MONEY_EMOJI),
            )
            for p in TICKET_PLANS
        ]
        super().__init__(
            placeholder="Seleziona un piano d'accesso",
            min_values=1, max_values=1, options=options,
            custom_id="snapplus:plan_select",
        )

    async def callback(self, interaction: discord.Interaction):
        plan = _plan_by_key(self.values[0])
        if not plan:
            await interaction.response.send_message("Piano non valido.", ephemeral=True)
            return

        channel = await _open_ticket(interaction, TICKET_PURCHASE_CATEGORY_ID, "purchase")
        if channel is None:
            return

        ltc     = await _usd_to_ltc(plan["usd"])
        ltc_str = f"{ltc} LTC" if ltc else "Chiedi allo staff (tasso non disponibile)"

        await channel.send(view=InvoiceView(plan["label"], plan["usd"], ltc_str))
        await interaction.followup.send(
            f"✅ Ticket acquisto aperto: {channel.mention}", ephemeral=True
        )


class PlanSelectView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=180)
        body = f"# {MONEY_EMOJI} Seleziona un piano\nScegli un piano per procedere al pagamento."
        c = discord.ui.Container(accent_colour=0x4A9EFF)
        c.add_item(discord.ui.TextDisplay(body))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(PlanSelect()))
        self.add_item(c)


class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Purchase", value="purchase",
                                 emoji=discord.PartialEmoji.from_str(MONEY_EMOJI)),
            discord.SelectOption(label="Support",  value="support",
                                 emoji=discord.PartialEmoji.from_str(GUIDE_EMOJI)),
        ]
        super().__init__(
            placeholder="Seleziona una categoria",
            min_values=1, max_values=1, options=options,
            custom_id="snapplus:ticket_category",
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "support":
            channel = await _open_ticket(interaction, TICKET_SUPPORT_CATEGORY_ID, "support")
            if channel is None:
                return
            await channel.send(view=SupportTicketView())
            await interaction.followup.send(
                f"✅ Ticket support aperto: {channel.mention}", ephemeral=True
            )
        else:
            await interaction.response.send_message(view=PlanSelectView(), ephemeral=True)


def _ticket_panel_body() -> str:
    return (
        f"# {TICKET_EMOJI} Purchase Tickets\n"
        f"Apri un ticket per acquistare l'accesso alle funzionalità del server."
    )

def _ticket_info_body() -> str:
    return (
        f"{ALERT_EMOJI} **Prezzi** — "
        f"12h: $5  ·  24h: $10  ·  48h: $20  ·  Lifetime: $450\n\n"
        f"{GUIDE_EMOJI} **Pagamento** — Solo Litecoin (LTC). Nessun altro metodo accettato."
    )

class TicketPanelView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_colour=0x4A9EFF)
        c.add_item(discord.ui.TextDisplay(_ticket_panel_body()))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.TextDisplay(_ticket_info_body()))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(TicketCategorySelect()))
        self.add_item(c)

# ── BOT ───────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    bot.add_view(TicketPanelView())
    bot.add_view(SupportTicketView())
    for g in bot.guilds:
        bot.tree.copy_global_to(guild=g)
        await bot.tree.sync(guild=g)
    print(f"Online come {bot.user}")

@bot.command(name="ticket")
async def ticket_panel_cmd(ctx):
    """!ticket — posta il panel nel canale configurato (solo admin)."""
    if not ctx.author.guild_permissions.administrator:
        return
    ch = bot.get_channel(TICKET_PANEL_CHANNEL_ID)
    if ch is None:
        await ctx.send("❌ Canale ticket panel non trovato.")
        return
    try:
        async for m in ch.history(limit=20):
            if m.author == bot.user:
                await m.delete()
    except Exception:
        pass
    await ch.send(view=TicketPanelView())
    try:
        await ctx.message.delete()
    except Exception:
        pass

bot.run(TOKEN)
