import asyncio
import os
import traceback
import aiohttp
import discord
from discord.ext import commands

TOKEN = os.getenv("TOKEN", "IL_TUO_TOKEN")

WELCOME_CHANNEL_ID          = 1562890044455526551
TICKET_SUPPORT_CATEGORY_ID  = 1562900594367270963   # SUPPORT TICKETS
TICKET_PURCHASE_CATEGORY_ID = 1562900617385480212   # PURCHASE TICKETS
STAFF_ROLE_ID               = 1562900424233848852
LTC_ADDRESS                 = "LZnytAtTzjGqUeLWHpkvhkK2U8z5f5fov5"
PRICE_USD                   = 10

CHANNEL_FEATURES_ID         = 1562901227254185994
CHANNEL_TICKETS_ID          = 1562901115803144315
GUILD_ID                    = 0  # non usato

# Link del pulsante "Premium Features" sotto il pannello !ticket
PREMIUM_FEATURES_URL = "https://discord.com/channels/1562551271792181341/1562901227254185994"

# Link del pulsante "Tutorial" sotto il pannello !freeaccesspanel
TUTORIAL_URL = "https://discord.com/channels/1562551271792181341/1562567885434523678"

ALERT_EMOJI    = "<a:Alert:1562891464432943124>"
QUESTION_EMOJI = "<:question:1562891360850284595>"
WARN_EMOJI     = "<a:warnings:1562891301760802938>"
GUIDE_EMOJI    = "<:guide:1562891148928884789>"
MONEY_EMOJI    = "<:money:1562891076006584373>"
SHOP_EMOJI     = "<a:shopping:1562891221423104072>"
TICKET_EMOJI   = "<:ticket:1562891010999062739>"

# ── NUOVE EMOJI ─────────────────────────────────────────────────────────────
DOWNLOAD_EMOJI = "<:download_discord:1563225797144350790>"
WINDOWS_EMOJI  = "<:windows:1563221221196300318>"
LINUX_EMOJI    = "<:linux:1563221292151480320>"
FOLDER_EMOJI   = "<:femboy:1563225407409361047>"
LOADING_EMOJI  = "<a:loading:1563226245557387324>"

# Immagine mostrata nell'embed del pannello !freeaccesspanel.
# Metti il file "free_builder_banner.png" nella STESSA cartella di bot.py.
FREE_BUILDER_IMAGE_FILENAME = "FREE_BUILDER_IMAGE_FILENAME.png"

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


# ── TICKET HELPERS ────────────────────────────────────────────────────────────
# Il topic del canale contiene:  owner:<id>   oppure   owner:<id>|ltc:<importo>
# Così dopo un riavvio del bot i messaggi dei ticket si ricostruiscono giusti.
def _topic_owner(topic: str):
    return (topic or "").split("|")[0]


def _ltc_from_topic(topic: str) -> str:
    if topic and "|ltc:" in topic:
        return topic.split("|ltc:", 1)[1]
    return ""


def _owner_id_from_topic(topic: str):
    try:
        return int(_topic_owner(topic).split(":", 1)[1])
    except Exception:
        return None


async def _find_user_ticket(guild: discord.Guild, user_id: int):
    for ch in guild.text_channels:
        if ch.category_id in {TICKET_SUPPORT_CATEGORY_ID, TICKET_PURCHASE_CATEGORY_ID}:
            if _topic_owner(ch.topic) == f"owner:{user_id}":
                return ch
    return None


async def _create_ticket_channel(interaction: discord.Interaction, category_id: int,
                                 kind: str, ltc_str: str = ""):
    """Returns (channel, error_message). Does NOT touch the interaction response."""
    guild = interaction.guild
    user  = interaction.user

    existing = await _find_user_ticket(guild, user.id)
    if existing:
        return None, f"{ALERT_EMOJI} You already have an open ticket: {existing.mention}"

    category = guild.get_channel(category_id)
    if category is None:
        try:
            category = await guild.fetch_channel(category_id)
        except Exception:
            category = None
    if category is None:
        return None, f"{WARN_EMOJI} Ticket category not found (check the category ID in the config)."

    me = guild.me
    if not category.permissions_for(me).manage_channels:
        return None, f"{WARN_EMOJI} I don't have **Manage Channels** permission in that category."

    staff_role = guild.get_role(STAFF_ROLE_ID)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user:               discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    topic = f"owner:{user.id}"
    if ltc_str:
        topic += f"|ltc:{ltc_str}"

    channel = await guild.create_text_channel(
        f"{kind}-{user.name}",
        category=category,
        overwrites=overwrites,
        topic=topic,
    )
    return channel, None


# ── BASE VIEW (logga gli errori invece di farli sparire) ──────────────────────
class BaseView(discord.ui.LayoutView):
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        traceback.print_exception(type(error), error, error.__traceback__)


# ── BUTTONS ───────────────────────────────────────────────────────────────────
class PingStaffButton(discord.ui.Button):
    def __init__(self, pinged: bool = False):
        super().__init__(
            label="Staff Pinged" if pinged else "Ping Staff",
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji.from_str(ALERT_EMOJI),
            custom_id="snap:ping_staff",
            disabled=pinged,
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            channel  = interaction.channel
            owner_id = _owner_id_from_topic(channel.topic)

            # Ricostruisco la view giusta in base alla categoria del ticket
            # (funziona anche dopo un riavvio del bot).
            if getattr(channel, "category_id", None) == TICKET_PURCHASE_CATEGORY_ID:
                new_view = PurchaseTicketView(_ltc_from_topic(channel.topic), pinged=True, owner_id=owner_id)
            else:
                new_view = SupportTicketView(pinged=True, owner_id=owner_id)

            await interaction.response.edit_message(view=new_view)
            await channel.send(
                content=f"<@&{STAFF_ROLE_ID}>",
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except Exception:
            traceback.print_exc()


class CloseTicketButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            emoji=discord.PartialEmoji.from_str(WARN_EMOJI),
            custom_id="snap:close_ticket",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            c = discord.ui.Container(accent_colour=WHITE)
            c.add_item(discord.ui.TextDisplay(
                f"{LOADING_EMOJI} **Closing ticket...**\nThis channel will be deleted in 5 seconds."
            ))
            view = discord.ui.LayoutView(timeout=None)
            view.add_item(c)
            await interaction.response.send_message(view=view)
            await asyncio.sleep(5)
            await interaction.channel.delete()
        except Exception:
            traceback.print_exc()


class PurchaseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Purchase",
            style=discord.ButtonStyle.success,
            emoji=discord.PartialEmoji.from_str(MONEY_EMOJI),
            custom_id="snap:purchase",
        )

    async def callback(self, interaction: discord.Interaction):
        # ACK FIRST — deve sempre avvenire entro 3s, qualunque cosa succeda.
        try:
            await interaction.response.send_message(f"{LOADING_EMOJI} Opening your ticket...", ephemeral=True)
        except Exception:
            traceback.print_exc()
            return

        try:
            ltc     = await _usd_to_ltc(PRICE_USD)
            ltc_str = f"{ltc} LTC" if ltc else "Ask staff (rate unavailable)"

            channel, err = await _create_ticket_channel(
                interaction, TICKET_PURCHASE_CATEGORY_ID, "purchase", ltc_str
            )
            if err:
                await interaction.edit_original_response(content=err)
                return

            await channel.send(view=PurchaseTicketView(ltc_str, owner_id=interaction.user.id))
            await interaction.edit_original_response(content=f"{TICKET_EMOJI} Ticket opened: {channel.mention}")
        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.edit_original_response(content=f"{WARN_EMOJI} Something went wrong: {e}")
            except Exception:
                pass


class SupportButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Support",
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji.from_str(GUIDE_EMOJI),
            custom_id="snap:support",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message(f"{LOADING_EMOJI} Opening your ticket...", ephemeral=True)
        except Exception:
            traceback.print_exc()
            return

        try:
            channel, err = await _create_ticket_channel(
                interaction, TICKET_SUPPORT_CATEGORY_ID, "support"
            )
            if err:
                await interaction.edit_original_response(content=err)
                return

            await channel.send(view=SupportTicketView(owner_id=interaction.user.id))
            await interaction.edit_original_response(content=f"{TICKET_EMOJI} Ticket opened: {channel.mention}")
        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.edit_original_response(content=f"{WARN_EMOJI} Something went wrong: {e}")
            except Exception:
                pass


# ── TICKET VIEWS (persistent — timeout=None) ──────────────────────────────────
class SupportTicketView(BaseView):
    def __init__(self, pinged: bool = False, owner_id: int = None):
        super().__init__(timeout=None)
        greet = f"Welcome <@{owner_id}>! Thanks for reaching out." if owner_id else "Welcome! Thanks for reaching out."

        c = discord.ui.Container(accent_colour=WHITE)
        c.add_item(discord.ui.TextDisplay(
            f"# {GUIDE_EMOJI} Support Ticket\n"
            f"-# Our team will be with you shortly"
        ))
        c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
        c.add_item(discord.ui.TextDisplay(
            f"{greet}\n"
            f"A staff member will reply as soon as possible."
        ))
        c.add_item(discord.ui.TextDisplay(
            f"**How to get help faster**\n"
            f"{QUESTION_EMOJI}  Describe your issue with as much detail as you can\n"
            f"{GUIDE_EMOJI}  Add screenshots or any useful info\n"
            f"{ALERT_EMOJI}  Press **Ping Staff** only when you're ready"
        ))
        c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
        c.add_item(discord.ui.ActionRow(PingStaffButton(pinged), CloseTicketButton()))
        self.add_item(c)


class PurchaseTicketView(BaseView):
    def __init__(self, ltc_str: str = "", pinged: bool = False, owner_id: int = None):
        super().__init__(timeout=None)
        greet = f"Welcome <@{owner_id}>! " if owner_id else ""

        c = discord.ui.Container(accent_colour=YELLOW)
        c.add_item(discord.ui.TextDisplay(
            f"# {SHOP_EMOJI} Purchase — Premium Access\n"
            f"-# Pay with Litecoin (LTC) · Access is granted after confirmation"
        ))
        c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
        c.add_item(discord.ui.TextDisplay(
            f"{greet}Send the exact amount to the address below to complete your purchase."
        ))
        c.add_item(discord.ui.TextDisplay(
            f"**{MONEY_EMOJI} Plan**\n```Premium Access — ${PRICE_USD} USD```"
        ))
        c.add_item(discord.ui.TextDisplay(
            f"**{MONEY_EMOJI} LTC Amount**\n```{ltc_str or '...'}```"
        ))
        c.add_item(discord.ui.TextDisplay(
            f"**{MONEY_EMOJI} Payment Address**\n```{LTC_ADDRESS}```"
        ))
        c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
        c.add_item(discord.ui.TextDisplay(
            f"{WARN_EMOJI} **Do NOT pay any staff member. Only use this address.**\n"
            f"-# Once your payment is confirmed, staff will grant you access."
        ))
        c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
        c.add_item(discord.ui.ActionRow(PingStaffButton(pinged), CloseTicketButton()))
        self.add_item(c)


# ── PANEL VIEW (persistent) ───────────────────────────────────────────────────
class TicketPanelView(BaseView):
    def __init__(self):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_colour=WHITE)
        c.add_item(discord.ui.TextDisplay(
            f"# {TICKET_EMOJI} Support Tickets\n"
            f"Need help or want to get access? Open a ticket and our team will assist you.\n\n"
            f"{MONEY_EMOJI} **Purchase** — Get Premium Access for **$10** via Litecoin.\n"
            f"{GUIDE_EMOJI} **Support** — Have a question or issue? We're here to help."
        ))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(PurchaseButton(), SupportButton()))
        self.add_item(c)


# ── PREMIUM FEATURES EMBED (sotto il pannello, solo link button) ──────────────
class PremiumFeaturesView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_colour=WHITE)
        c.add_item(discord.ui.TextDisplay(
            f"# {SHOP_EMOJI} Premium Features\n"
            f"Curious about what Premium Access includes? Check out every feature before you buy."
        ))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(
            discord.ui.Button(
                label="Premium Features",
                style=discord.ButtonStyle.link,
                emoji=discord.PartialEmoji.from_str(MONEY_EMOJI),
                url=PREMIUM_FEATURES_URL,
            ),
        ))
        self.add_item(c)


# ── WELCOME VIEW (V2) ─────────────────────────────────────────────────────────
def _welcome_view(member: discord.Member) -> discord.ui.LayoutView:
    guild_id = member.guild.id
    view = discord.ui.LayoutView(timeout=None)
    c = discord.ui.Container(accent_colour=WHITE)
    c.add_item(discord.ui.TextDisplay(
        f"# {ALERT_EMOJI} Welcome, {member.mention}!\n"
        f"Glad to have you in **{member.guild.name}**. Check out the channels below to get started."
    ))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.ActionRow(
        discord.ui.Button(
            label="Premium Features",
            style=discord.ButtonStyle.link,
            emoji=discord.PartialEmoji.from_str(MONEY_EMOJI),
            url=f"https://discord.com/channels/{guild_id}/{CHANNEL_FEATURES_ID}",
        ),
        discord.ui.Button(
            label="Open a Ticket",
            style=discord.ButtonStyle.link,
            emoji=discord.PartialEmoji.from_str(TICKET_EMOJI),
            url=f"https://discord.com/channels/{guild_id}/{CHANNEL_TICKETS_ID}",
        ),
    ))
    view.add_item(c)
    return view


# ── FREE ACCESS: GUIDE TEXT (placeholder — rifiniscila tu) ────────────────────
def _builder_guide(os_name: str) -> str:
    if os_name == "windows":
        return (
            f"**{GUIDE_EMOJI} Quick Setup Guide — Windows**\n"
            f"1. Extract the downloaded `.zip` file to a folder of your choice\n"
            f"2. Right-click `setup.exe` and run it **as Administrator**\n"
            f"3. Follow the on-screen installer steps\n"
            f"4. Launch the builder from the Start Menu shortcut\n"
            f"-# If Windows Defender flags it, add an exception for the folder."
        )
    return (
        f"**{GUIDE_EMOJI} Quick Setup Guide — Linux**\n"
        f"1. Extract the downloaded `.tar.gz` archive\n"
        f"2. Open a terminal in that folder\n"
        f"3. Run `chmod +x setup.sh && ./setup.sh`\n"
        f"4. Launch the builder with `./builder`\n"
        f"-# Make sure you have the required dependencies installed first."
    )


# ── FREE ACCESS: DM — OS SELECT MENU ───────────────────────────────────────────
class OSSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Windows",
                value="windows",
                emoji=discord.PartialEmoji.from_str(WINDOWS_EMOJI),
                description="Download the builder for Windows",
            ),
            discord.SelectOption(
                label="Linux",
                value="linux",
                emoji=discord.PartialEmoji.from_str(LINUX_EMOJI),
                description="Download the builder for Linux",
            ),
        ]
        super().__init__(
            placeholder="Select your Operating System",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="snap:os_select",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            os_choice = self.values[0]
            emoji     = WINDOWS_EMOJI if os_choice == "windows" else LINUX_EMOJI
            label     = "Windows" if os_choice == "windows" else "Linux"

            c = discord.ui.Container(accent_colour=WHITE)
            c.add_item(discord.ui.TextDisplay(
                f"# {FOLDER_EMOJI} Here is your file for {label}\n"
                f"-# {emoji}  Builder — {label} edition"
            ))
            c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
            c.add_item(discord.ui.TextDisplay(_builder_guide(os_choice)))
            c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
            c.add_item(discord.ui.TextDisplay(
                f"{WARN_EMOJI} Attach the actual build file here before sending to users."
            ))

            result_view = discord.ui.LayoutView(timeout=None)
            result_view.add_item(c)

            await interaction.response.send_message(view=result_view)
        except Exception:
            traceback.print_exc()


class OSSelectView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_colour=WHITE)
        c.add_item(discord.ui.TextDisplay(
            f"# {FOLDER_EMOJI} Femboy Builder\n"
            f"Select your Operating System"
        ))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(OSSelect()))
        c.add_item(discord.ui.ActionRow(
            discord.ui.Button(
                label="Tutorial",
                style=discord.ButtonStyle.link,
                emoji=discord.PartialEmoji.from_str(GUIDE_EMOJI),
                url=TUTORIAL_URL,
            ),
        ))
        self.add_item(c)


# ── FREE ACCESS: PANEL ────────────────────────────────────────────────────────
class FreeAccessDownloadButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Download",
            style=discord.ButtonStyle.success,
            emoji=discord.PartialEmoji.from_str(DOWNLOAD_EMOJI),
            custom_id="snap:freeaccess_download",
        )

    async def callback(self, interaction: discord.Interaction):
        # ACK FIRST con un messaggio di "loading", poi aggiorno il risultato.
        try:
            await interaction.response.send_message(f"{LOADING_EMOJI} Sending in dms...", ephemeral=True)
        except Exception:
            traceback.print_exc()
            return

        try:
            await interaction.user.send(view=OSSelectView())
            await interaction.edit_original_response(content=f"{DOWNLOAD_EMOJI} Check your DMs!")
        except discord.Forbidden:
            await interaction.edit_original_response(
                content=f"{WARN_EMOJI} I can't DM you — please enable DMs from server members and try again."
            )
        except Exception as e:
            traceback.print_exc()
            try:
                await interaction.edit_original_response(content=f"{WARN_EMOJI} Something went wrong: {e}")
            except Exception:
                pass


class FreeAccessPanelView(BaseView):
    def __init__(self):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_colour=WHITE)
        c.add_item(discord.ui.TextDisplay(
            f"# {FOLDER_EMOJI} Free Builder\n"
            f"Press the button below to get **access to the free builder**.\n"
            f"-# A **setup guide** will be sent to your DMs together with the **download**."
        ))
        c.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem(media=f"attachment://{FREE_BUILDER_IMAGE_FILENAME}")
        ))
        c.add_item(discord.ui.Separator())
        c.add_item(discord.ui.ActionRow(
            FreeAccessDownloadButton(),
            discord.ui.Button(
                label="Tutorial",
                style=discord.ButtonStyle.link,
                emoji=discord.PartialEmoji.from_str(GUIDE_EMOJI),
                url=TUTORIAL_URL,
            ),
        ))
        self.add_item(c)


# ── BOT ───────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class SnapBot(commands.Bot):
    async def setup_hook(self):
        # Registrate UNA SOLA VOLTA, prima della connessione (on_ready può scattare più volte)
        self.add_view(TicketPanelView())
        self.add_view(SupportTicketView())
        self.add_view(PurchaseTicketView())
        self.add_view(FreeAccessPanelView())
        self.add_view(OSSelectView())


bot = SnapBot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"Online as {bot.user} | discord.py {discord.__version__}")
    print("[!] Se hai cambiato codice, rilancia !ticket / !freeaccesspanel per postare un pannello NUOVO.")
    print("[!] Assicurati che giri UNA SOLA istanza del bot.")


@bot.event
async def on_interaction(interaction: discord.Interaction):
    # Solo log di debug: mostra ogni click sui pulsanti in console.
    if interaction.type == discord.InteractionType.component:
        cid = (interaction.data or {}).get("custom_id")
        print(f"[CLICK] {interaction.user} -> {cid}")


@bot.event
async def on_member_join(member: discord.Member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch is None:
        return
    try:
        await ch.send(
            view=_welcome_view(member),
            allowed_mentions=discord.AllowedMentions(users=True),
        )
    except Exception:
        traceback.print_exc()


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
    await ctx.channel.send(view=TicketPanelView())
    await ctx.channel.send(view=PremiumFeaturesView())
    try:
        await ctx.message.delete()
    except Exception:
        pass


@bot.command(name="freeaccesspanel")
async def free_access_panel_cmd(ctx):
    if not ctx.author.guild_permissions.administrator:
        return
    try:
        async for m in ctx.channel.history(limit=20):
            if m.author == bot.user:
                await m.delete()
    except Exception:
        pass

    image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), FREE_BUILDER_IMAGE_FILENAME)
    file = discord.File(image_path, filename=FREE_BUILDER_IMAGE_FILENAME)
    await ctx.channel.send(view=FreeAccessPanelView(), file=file)
    try:
        await ctx.message.delete()
    except Exception:
        pass


bot.run(TOKEN)
