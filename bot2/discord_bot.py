import discord
from discord import app_commands
from discord.ui import Select, View
import os
import json
from keep_alive import keep_alive
from datetime import datetime, timedelta
import asyncio
from config import BOT_CONFIGS

def load_json_file(filename, default_data):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(filename, 'w') as f:
            json.dump(default_data, f)
        return default_data

def save_json_file(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

class ServerSelectView(View):
    def __init__(self, guilds):
        super().__init__()
        options = [
            discord.SelectOption(label=f"{i+1}. {guild.name}", value=str(guild.id)) 
            for i, guild in enumerate(guilds)
        ]
        self.select = Select(placeholder="Select a server...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        guild_id = self.select.values[0]
        guild = interaction.client.get_guild(int(guild_id))
        if guild:
            if not guild.me.guild_permissions.create_instant_invite:
                embed = discord.Embed(
                    title="❌ Error",
                    description=f"I don't have permission to create invites in **{guild.name}**.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            channel_to_invite = None
            if guild.system_channel and guild.system_channel.permissions_for(guild.me).create_instant_invite:
                 channel_to_invite = guild.system_channel
            else:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).create_instant_invite:
                        channel_to_invite = channel
                        break
            
            if channel_to_invite:
                try:
                    invite = await channel_to_invite.create_invite(max_age=0, max_uses=0)
                    embed = discord.Embed(
                        title=f"✅ Invite to {guild.name}",
                        description=f"Here is your unlimited invite link:\n[CLICK HERE]({invite.url})",
                        color=discord.Color.green()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                except discord.HTTPException:
                    embed = discord.Embed(
                        title="❌ Error",
                        description=f"An error occurred while creating the invite for **{guild.name}**.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                 embed = discord.Embed(
                    title="❌ Error",
                    description=f"I couldn't find a suitable channel to create an invite in **{guild.name}**.",
                    color=discord.Color.red()
                )
                 await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Could not find that server.", ephemeral=True)

class BotClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = app_commands.CommandTree(self)
        self.nickname_cooldowns = {}
        self.reset_nickname_cooldowns = {}
        self.rules_message_ids = {}
        self.refresh_locks = {}
        self.pending_refreshes = {}
        self.whitelist = load_json_file('whitelist.json', [])
        self.channel_config = load_json_file('channel_config.json', {})
        self.invite_access = load_json_file('invite_access.json', [1400142512798302332])
        self.whitelist_access = load_json_file('whitelist_access.json', [1400142512798302332])

    async def setup_hooks(self):
        for guild in self.guilds:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

    async def on_ready(self):
        await self.setup_hooks()
        print(f"LOGGED IN {self.user}")
        print(f"Bot is ready and operating on {len(self.guilds)} server(s).")

    async def _schedule_refresh_rules(self, channel):
        if channel.id in self.pending_refreshes:
            self.pending_refreshes[channel.id].cancel()
        task = asyncio.create_task(self._execute_refresh_after_delay(channel))
        self.pending_refreshes[channel.id] = task

    async def _execute_refresh_after_delay(self, channel):
        await asyncio.sleep(10.1)
        lock = self.refresh_locks.setdefault(channel.id, asyncio.Lock())
        async with lock:
            rules_embed = discord.Embed(
                title="📜 Nickname Rules:",
                description=(
                    "1. All fonts are allowed, Also Bengali (Bangla) names and Emojis are allowed.\n\n"
                    "2. Offensive or inappropriate names are not allowed.\n\n"
                    "3. If the authority observes your inappropriate name, you may be punished.\n\n"
                    "4. You can reset your nickname using this command `!reset_nickname`"
                ),
                color=discord.Color.from_rgb(47, 49, 54)
            )
            new_rules_msg = await channel.send(embed=rules_embed)

            old_message_id = self.rules_message_ids.pop(channel.id, None)
            if old_message_id:
                try:
                    old_msg = await channel.fetch_message(old_message_id)
                    await old_msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
            self.rules_message_ids[channel.id] = new_rules_msg.id

    async def on_message(self, message):
        if message.author == self.user or not message.guild:
            return

        guild_id_str = str(message.guild.id)
        target_channels = self.channel_config.get(guild_id_str, [])
        if message.channel.id not in target_channels:
            return

        member = message.guild.get_member(message.author.id)
        old_nickname = member.display_name
        
        try:
            await message.delete(delay=2)
        except (discord.Forbidden, discord.NotFound):
            print(f"ERROR: Could not delete user message in '{message.channel.name}'.")

        content = message.content.strip()
        user_id = member.id
        is_whitelisted = user_id in self.whitelist
        
        new_nickname = None
        error_occurred = False

        if content.lower() == "!reset_nickname":
            if not is_whitelisted:
                if user_id in self.reset_nickname_cooldowns and datetime.now() < self.reset_nickname_cooldowns[user_id]:
                    remaining_time = self.reset_nickname_cooldowns[user_id] - datetime.now()
                    hours, remainder = divmod(remaining_time.total_seconds(), 3600)
                    minutes, _ = divmod(remainder, 60)
                    embed = discord.Embed(
                        title="⏳ Cooldown",
                        description=f"{member.mention}, you can use `!reset_nickname` again in **{int(hours)}** hours and **{int(minutes)}** minutes.",
                        color=discord.Color.orange()
                    )
                    sent_message = await message.channel.send(embed=embed)
                    await sent_message.delete(delay=10)
                    return
            
            try:
                await member.edit(nick=None)
                new_nickname = member.name
                if not is_whitelisted:
                    self.reset_nickname_cooldowns[user_id] = datetime.now() + timedelta(hours=2)
            except discord.Forbidden:
                error_occurred = True
                embed = discord.Embed(
                    title="❌ Error",
                    description=f"I don't have permission to change {member.mention}'s nickname. Please contact an administrator.",
                    color=discord.Color.red()
                )
                sent_message = await message.channel.send(embed=embed)
                await sent_message.delete(delay=10)
        else:
            if not is_whitelisted:
                if user_id in self.nickname_cooldowns and datetime.now() < self.nickname_cooldowns[user_id]:
                    remaining_time = self.nickname_cooldowns[user_id] - datetime.now()
                    minutes, seconds = divmod(remaining_time.total_seconds(), 60)
                    embed = discord.Embed(
                        title="⏳ Cooldown",
                        description=f"{member.mention}, you can change your nickname again in {int(minutes)} minutes and {int(seconds)} seconds.",
                        color=discord.Color.orange()
                    )
                    sent_message = await message.channel.send(embed=embed)
                    await sent_message.delete(delay=10)
                    return

            if len(content) > 32:
                error_occurred = True
                embed = discord.Embed(
                    title="❌ Error",
                    description="Your nickname can't be longer than 32 characters.",
                    color=discord.Color.red()
                )
                sent_message = await message.channel.send(embed=embed)
                await sent_message.delete(delay=10)
                return

            try:
                await member.edit(nick=content)
                new_nickname = content
                if not is_whitelisted:
                    self.nickname_cooldowns[user_id] = datetime.now() + timedelta(minutes=30)
            except discord.Forbidden:
                error_occurred = True
                embed = discord.Embed(
                    title="❌ Error",
                    description=f"I don't have permission to change {member.mention}'s nickname. Please contact an administrator.",
                    color=discord.Color.red()
                )
                sent_message = await message.channel.send(embed=embed)
                await sent_message.delete(delay=10)
        
        if not error_occurred and new_nickname is not None:
            embed = discord.Embed(
                title="🔄 Nickname Has Been Changed",
                description=f"{member.mention} Your Nickname Has Been Changed!",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="BEFORE CHANGED    ", value=f"`{old_nickname}`", inline=True)
            embed.add_field(name="AFTER CHANGED     ", value=f"`{new_nickname}`", inline=True)
            embed.set_footer(text=f"Request ID: {message.id}")
            
            await message.channel.send(embed=embed)

        await self._schedule_refresh_rules(message.channel)

@app_commands.command(name="help", description="Shows the list of commands for administrators.")
@app_commands.default_permissions(administrator=True)
async def help_command(interaction: discord.Interaction):
    bot = interaction.client
    user_id = interaction.user.id

    if user_id in bot.whitelist_access:
        embed = discord.Embed(
            title="👑 Administrator Commands",
            description="Here are the commands you can use:",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Nickname Channel Management",
            value="`/channel add` - Adds a channel for editing nicknames."
                  "`/channel remove` - Removes a channel for changing nickname."
                  "`/channel list` - Lists the current nickname change channels.",
            inline=False
        )
        embed.add_field(
            name="Whitelist Cooldown Management",
            value="`/cooldown add` - Adds a user to the cooldown whitelist."
                  "`/cooldown remove` - Removes a user from the cooldown whitelist.",
            inline=False
        )
        embed.add_field(
            name="Whitelist Access Management",
            value="`/access add` - Adds a user to the access list for whitelist management."
                  "`/access remove` - Removes a user from the access list."
                  "`/access list` - List users with management access.",
            inline=False
        )
        embed.add_field(
            name="Invitation Management",
            value="`/invite-access add` - Adds a user to the invitation access list."
                  "`/invite-access remove` - Removes a user from the invitation access list."
                  "`/servers` - Lists the servers where the bot is located."
                  "`/invite` - Create a unique server invite.",
            inline=False
        )
    else:

        embed = discord.Embed(
            title="👑 Administrator Commands",
            description="Here are the commands you can use:",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Nickname Channel Management",
            value="`/channel add` - Adds a channel for editing nicknames."
                  "`/channel remove` - Removes a channel for changing nickname."
                  "`/channel list` - Lists the current nickname change channels.",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.command(name="servers", description="List servers the bot is in.")
async def servers(interaction: discord.Interaction):
    bot = interaction.client
    if interaction.user.id not in bot.invite_access:
        embed = discord.Embed(
            title="❌ Error",
            description="You do not have permission to use this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    view = ServerSelectView(bot.guilds)
    await interaction.response.send_message("Select a server from the list:", view=view, ephemeral=True)

@app_commands.command(name="invite", description="Create a one-time invite to the server.")
async def invite(interaction: discord.Interaction):
    bot = interaction.client
    if interaction.user.id not in bot.invite_access:
        embed = discord.Embed(
            title="❌ Error",
            description="You do not have permission to use this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        invite = await interaction.channel.create_invite(max_uses=1, unique=True)
        embed = discord.Embed(
            title="✅ Invite Created",
            description=f"Here is your one-time invite link: [CLICK HERE TO JOIN]({invite.url})",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.Forbidden:
        embed = discord.Embed(
            title="❌ Error",
            description="I don't have permission to create invites in this channel.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.default_permissions(administrator=True)
class AccessCommands(app_commands.Group):
    def __init__(self, bot: BotClient, *args, **kwargs):
        super().__init__(name="access", description="Manage whitelist access", *args, **kwargs)
        self.bot = bot

    @app_commands.command(name="add", description="Add a user to the whitelist access list.")
    async def add(self, interaction: discord.Interaction, user: discord.Member):
        if interaction.user.id != 1400142512798302332 or 1420082026752508017:
            embed = discord.Embed(
                title="❌ Error",
                description="You do not have permission to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if user.id in self.bot.whitelist_access:
            embed = discord.Embed(
                title="❌ Error",
                description=f"{user.mention} already has access to manage the whitelist.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.whitelist_access.append(user.id)
            save_json_file('whitelist_access.json', self.bot.whitelist_access)
            embed = discord.Embed(
                title="✅ Success",
                description=f"{user.mention} now has access to manage the whitelist.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remove", description="Remove a user from the whitelist access list.")
    async def remove(self, interaction: discord.Interaction, user: discord.Member):
        if interaction.user.id != 1400142512798302332:
            embed = discord.Embed(
                title="❌ Error",
                description="You do not have permission to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if user.id not in self.bot.whitelist_access:
            embed = discord.Embed(
                title="❌ Error",
                description=f"{user.mention} does not have access to manage the whitelist.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.whitelist_access.remove(user.id)
            save_json_file('whitelist_access.json', self.bot.whitelist_access)
            embed = discord.Embed(
                title="✅ Success",
                description=f"{user.mention} no longer has access to manage the whitelist.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="list", description="List users with whitelist access.")
    async def list(self, interaction: discord.Interaction):
        if interaction.user.id not in self.bot.whitelist_access:
            embed = discord.Embed(
                title="❌ Error",
                description="You do not have permission to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not self.bot.whitelist_access:
            embed = discord.Embed(
                title="ℹ️ Whitelist Access",
                description="No users are configured to manage the whitelist.",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            mentions = [f"<@{uid}>" for uid in self.bot.whitelist_access]
            embed = discord.Embed(
                title="📢 Whitelist Access",
                description=f"Users with access: {', '.join(mentions)}",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.default_permissions(administrator=True)
class InviteAccessCommands(app_commands.Group):
    def __init__(self, bot: BotClient, *args, **kwargs):
        super().__init__(name="invite-access", description="Manage invite access", *args, **kwargs)
        self.bot = bot

    @app_commands.command(name="add", description="Add a user to the invite access list.")
    async def add(self, interaction: discord.Interaction, user: discord.Member):
        if interaction.user.id != 1400142512798302332:
            embed = discord.Embed(
                title="❌ Error",
                description="You do not have permission to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if user.id in self.bot.invite_access:
            embed = discord.Embed(
                title="❌ Error",
                description=f"{user.mention} already has access to the invite command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.invite_access.append(user.id)
            save_json_file('invite_access.json', self.bot.invite_access)
            embed = discord.Embed(
                title="✅ Success",
                description=f"{user.mention} now has access to the invite command.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remove", description="Remove a user from the invite access list.")
    async def remove(self, interaction: discord.Interaction, user: discord.Member):
        if interaction.user.id != 1400142512798302332:
            embed = discord.Embed(
                title="❌ Error",
                description="You do not have permission to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if user.id not in self.bot.invite_access:
            embed = discord.Embed(
                title="❌ Error",
                description=f"{user.mention} does not have access to the invite command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.invite_access.remove(user.id)
            save_json_file('invite_access.json', self.bot.invite_access)
            embed = discord.Embed(
                title="✅ Success",
                description=f"{user.mention} no longer has access to the invite command.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.default_permissions(administrator=True)
class ChannelCommands(app_commands.Group):
    def __init__(self, bot: BotClient, *args, **kwargs):
        super().__init__(name="channel", description="Manage nickname channels", *args, **kwargs)
        self.bot = bot

    @app_commands.command(name="add", description="Add a channel for nickname changes.")
    async def add(self, interaction: discord.Interaction, channel: discord.TextChannel):
        guild_id_str = str(interaction.guild.id)
        
        if guild_id_str not in self.bot.channel_config:
            self.bot.channel_config[guild_id_str] = []

        if channel.id in self.bot.channel_config[guild_id_str]:
            embed = discord.Embed(
                title="❌ Error",
                description=f"{channel.mention} is already a target channel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.channel_config[guild_id_str].append(channel.id)
            save_json_file('channel_config.json', self.bot.channel_config)
            embed = discord.Embed(
                title="✅ Success",
                description=f"{channel.mention} has been added as a target channel.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remove", description="Remove a channel for nickname changes.")
    async def remove(self, interaction: discord.Interaction, channel: discord.TextChannel):
        guild_id_str = str(interaction.guild.id)

        if guild_id_str not in self.bot.channel_config or channel.id not in self.bot.channel_config[guild_id_str]:
            embed = discord.Embed(
                title="❌ Error",
                description=f"{channel.mention} is not a target channel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.channel_config[guild_id_str].remove(channel.id)
            save_json_file('channel_config.json', self.bot.channel_config)
            embed = discord.Embed(
                title="✅ Success",
                description=f"{channel.mention} has been removed as a target channel.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


    @app_commands.command(name="list", description="List the current nickname change channels.")
    async def list(self, interaction: discord.Interaction):
        guild_id_str = str(interaction.guild.id)
        channel_ids = self.bot.channel_config.get(guild_id_str, [])
        
        if not channel_ids:
            embed = discord.Embed(
                title="ℹ️ Target Channels",
                description="There are no target channels configured for this server.",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            mentions = [f"<#{cid}>" for cid in channel_ids]
            embed = discord.Embed(
                title="📢 Target Channels",
                description=f"Current target channels: {', '.join(mentions)}",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.default_permissions(administrator=True)
class CooldownCommands(app_commands.Group):
    def __init__(self, bot: BotClient, *args, **kwargs):
        super().__init__(name="cooldown", description="Manage cooldown whitelist", *args, **kwargs)
        self.bot = bot

    @app_commands.command(name="add", description="Add a user to the cooldown whitelist.")
    async def add(self, interaction: discord.Interaction, user: discord.Member):
        if interaction.user.id not in self.bot.whitelist_access:
            embed = discord.Embed(
                title="❌ Error",
                description="You do not have permission to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if user.id in self.bot.whitelist:
            embed = discord.Embed(
                title="❌ Error",
                description=f"{user.mention} is already whitelisted.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.whitelist.append(user.id)
            save_json_file('whitelist.json', self.bot.whitelist)
            embed = discord.Embed(
                title="✅ Success",
                description=f"{user.mention} is now exempt from cooldowns.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remove", description="Remove a user from the cooldown whitelist.")
    async def remove(self, interaction: discord.Interaction, user: discord.Member):
        if interaction.user.id not in self.bot.whitelist_access:
            embed = discord.Embed(
                title="❌ Error",
                description="You do not have permission to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if user.id not in self.bot.whitelist:
            embed = discord.Embed(
                title="❌ Error",
                description=f"{user.mention} is not whitelisted.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            self.bot.whitelist.remove(user.id)
            save_json_file('whitelist.json', self.bot.whitelist)
            embed = discord.Embed(
                title="✅ Success",
                description=f"{user.mention} is no longer exempt from cooldowns.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def main():
    print("DEBUG: Main function started.")
    bot_configs = BOT_CONFIGS
    print(f"DEBUG: Loaded {len(bot_configs)} bot configs.")

    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    intents.members = True
    intents.guilds = True
    intents.invites = True

    print("DEBUG: Starting keep_alive server.")
    keep_alive()
    print("DEBUG: keep_alive server started.")

    async with asyncio.TaskGroup() as tg:
        for i, config in enumerate(bot_configs):
            token = config.get("token")
            if not token:
                print(f"DEBUG: Bot config {i+1} is missing a token, skipping.")
                continue

            print(f"DEBUG: Creating bot instance {i+1}.")
            bot = BotClient(intents=intents)
            bot.tree.add_command(CooldownCommands(bot))
            
            bot.tree.add_command(ChannelCommands(bot))
            bot.tree.add_command(invite)
            bot.tree.add_command(InviteAccessCommands(bot))
            bot.tree.add_command(servers)
            bot.tree.add_command(AccessCommands(bot))
            bot.tree.add_command(help_command)
            print(f"DEBUG: Starting bot instance {i+1}.")
            tg.create_task(bot.start(token))

    print("DEBUG: All bot tasks created.")

if __name__ == "__main__":
    asyncio.run(main())