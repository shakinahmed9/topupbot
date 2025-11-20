require("dotenv").config();
const { Client, GatewayIntentBits, PermissionFlagsBits } = require("discord.js");

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

client.on("ready", () => {
  console.log(`🟢 Bot Ready: ${client.user.tag}`);
  client.user.setActivity("FF Order System 💎");
});

// MESSAGE SYSTEM
client.on("messageCreate", async (msg) => {
  if (msg.author.bot) return;

  // ---- COMMANDS ---- //

  if (msg.content === "!help") {
    msg.reply(`
📌 **FF Diamond Order Bot Commands**

\`!setinput\` → Set order taking channel  
\`!setstore\` → Set order storage/log channel  
\`!addadmin @user\` → Make a user admin  
\`!status <orderID> <status>\` → Update order status  
`);
  }

  // SET INPUT CHANNEL
  if (msg.content === "!setinput") {
    if (!msg.member.permissions.has(PermissionFlagsBits.Administrator))
      return msg.reply("❌ Only Admin can do this!");
      
    settings.inputChannel = msg.channel.id;
    return msg.reply("📌 Order input channel set!");
  }

  // SET STORE CHANNEL
  if (msg.content === "!setstore") {
    if (!msg.member.permissions.has(PermissionFlagsBits.Administrator))
      return msg.reply("❌ Only Admin can do this!");
      
    settings.storeChannel = msg.channel.id;
    return msg.reply("📦 Order storage channel set!");
  }

  // ADD ADMIN
  if (msg.content.startsWith("!addadmin")) {
    if (!msg.member.permissions.has(PermissionFlagsBits.Administrator))
      return msg.reply("❌ You don't have permission!");

    const user = msg.mentions.users.first();
    if (!user) return msg.reply("⚠️ Mention a user!");

    settings.admins.push(user.id);
    return msg.reply(`👑 <@${user.id}> added as admin.`);
  }

  // ---- ORDER CREATION ---- //
  if (msg.channel.id === settings.inputChannel && settings.storeChannel) {

    settings.orderCount++;
    const orderID = settings.orderCount;

    msg.reply(`📩 **Order Received**  
🆔 Order ID: **${orderID}**
💎 Details: ${msg.content}
⌛ Status: **Pending**
`);

    const storeChannel = client.channels.cache.get(settings.storeChannel);

    const message = await storeChannel.send(
      `📦 **Order #${orderID}**
👤 User: <@${msg.author.id}>
💎 Order: ${msg.content}
📌 Status: **Pending**
`
    );

    message.pin();
  }

  // ---- STATUS UPDATE ---- //
  if (msg.content.startsWith("!status")) {
    const args = msg.content.split(" ");
    const orderID = args[1];
    const newStatus = args.slice(2).join(" ");

    if (!settings.admins.includes(msg.author.id))
      return msg.reply("🚫 Only admins can update order!");
    
    const storeChannel = client.channels.cache.get(settings.storeChannel);
    const messages = await storeChannel.messages.fetch({ limit: 100 });

    const target = messages.find(m => m.content.includes(`Order #${orderID}`));

    if (!target) return msg.reply("❌ Order not found!");

    const updated = target.content.replace(/Status: \*\*(.*)\*\*/, `Status: **${newStatus}**`);
    target.edit(updated);

    msg.reply(`✅ Order #${orderID} updated to **${newStatus}**`);
  }
});

// LOGIN
client.login(process.env.TOKEN);
