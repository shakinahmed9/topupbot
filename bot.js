require("dotenv").config();
const { 
  Client, 
  GatewayIntentBits, 
  PermissionFlagsBits, 
  ActionRowBuilder, 
  ButtonBuilder, 
  ButtonStyle 
} = require("discord.js");

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent
  ]
});

let settings = {
  inputChannel: null,
  storeChannel: null,
  admins: [],
  orderCount: 0
};

// ---------------- READY ----------------
client.on("ready", () => {
  console.log(`🟢 Bot Online: ${client.user.tag}`);
  client.user.setActivity("FF Diamond Store 💎");
});

// ---------------- MESSAGE LISTENER ----------------
client.on("messageCreate", async (msg) => {
  if (msg.author.bot) return;

  // HELP COMMAND
  if (msg.content === "!help") {
    msg.reply(`📌 **Commands:**
\`!setinput\` → Set order channel  
\`!setstore\` → Set storage/log channel  
\`!addadmin @user\` → Add admin  
\`!postbuttons\` → Create diamond button menu  
\`!status <ID> <Processing/Done/Cancel>\` → Update status`);
  }

  // SET INPUT CHANNEL
  if (msg.content === "!setinput") {
    if (!msg.member.permissions.has(PermissionFlagsBits.Administrator))
      return msg.reply("❌ Only admin can do this!");

    settings.inputChannel = msg.channel.id;
    return msg.reply("📥 Order input channel set!");
  }

  // SET STORE CHANNEL
  if (msg.content === "!setstore") {
    if (!msg.member.permissions.has(PermissionFlagsBits.Administrator))
      return msg.reply("❌ Only admin can do this!");

    settings.storeChannel = msg.channel.id;
    return msg.reply("📦 Order storage channel set!");
  }

  // ADD ADMIN
  if (msg.content.startsWith("!addadmin")) {
    if (!msg.member.permissions.has(PermissionFlagsBits.Administrator))
      return msg.reply("❌ No permission!");

    const user = msg.mentions.users.first();
    if (!user) return msg.reply("⚠️ Mention user!");

    settings.admins.push(user.id);
    return msg.reply(`👑 <@${user.id}> is now admin.`);
  }

  // POST BUTTONS
  if (msg.content === "!postbuttons") {
    if (!settings.inputChannel) return msg.reply("⚠️ First set input channel.");

    const row = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId("100").setLabel("100 💎").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("210").setLabel("210 💎").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("500").setLabel("500 💎").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("custom").setLabel("Custom Order").setStyle(ButtonStyle.Secondary)
    );

    msg.reply({ content: "👇 Select your Diamond Pack:", components: [row] });
  }

  // MESSAGE BASED ORDER
  if (msg.channel.id === settings.inputChannel && settings.storeChannel) {
    settings.orderCount++;
    handleOrder(msg.author, msg.content, msg);
  }

});

// ---------------- BUTTON HANDLING ----------------
client.on("interactionCreate", async interaction => {
  if (!interaction.isButton()) return;

  const options = {
    "100": "100 Diamond",
    "210": "210 Diamond",
    "500": "500 Diamond",
    "custom": "Custom Request (User Will Type)"
  };

  if (!settings.storeChannel) return interaction.reply("⚠ Order system not set!");

  settings.orderCount++;

  handleOrder(interaction.user, options[interaction.customId], interaction);
});

// ---------------- PROCESS ORDER FUNCTION ----------------
async function handleOrder(user, text, place) {
  const id = ++settings.orderCount;

  await place.reply(`📩 Order Received  
🆔 Order: **#${id}**
💎 ${text}
Status: **Pending**
`);

  const storeChannel = client.channels.cache.get(settings.storeChannel);

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(`p_${id}`).setLabel("Processing").setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId(`d_${id}`).setLabel("Done").setStyle(ButtonStyle.Success),
    new ButtonBuilder().setCustomId(`c_${id}`).setLabel("Cancel").setStyle(ButtonStyle.Danger)
  );

  const message = await storeChannel.send({
    content: `📦 **Order #${id}**
👤 User: <@${user.id}>
💎 ${text}
📌 Status: **Pending**`,
    components: [row]
  });

  message.pin();
}

// ---------------- STATUS UPDATE ----------------
client.on("interactionCreate", async interaction => {
  if (!interaction.isButton()) return;

  const [action, id] = interaction.customId.split("_");

  if (!settings.admins.includes(interaction.user.id))
    return interaction.reply({ content: "🚫 Only admins can update!", ephemeral: true });

  const statuses = {
    "p": "Processing",
    "d": "Completed",
    "c": "Cancelled"
  };

  const storeChannel = client.channels.cache.get(settings.storeChannel);
  const messages = await storeChannel.messages.fetch({ limit: 100 });
  const target = messages.find(m => m.content.includes(`Order #${id}`));

  const updated = target.content.replace(/Status: \*\*(.*)\*\*/, `Status: **${statuses[action]}**`);
  target.edit(updated);

  interaction.reply({ content: `✅ Order #${id} updated to **${statuses[action]}**`, ephemeral: true });
});

// ---------------- LOGIN ----------------
client.login(process.env.TOKEN);
