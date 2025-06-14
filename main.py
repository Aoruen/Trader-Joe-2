import os
import discord
from discord.ext import commands
import random
import re
from openai import OpenAI
from flask import Flask
import threading
import aiohttp
import asyncio

# Environment Variables
TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is missing!")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable is missing!")

# Set up OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Remove default help command
bot.remove_command("help")

# Normalize helper
def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())

# Split long messages
def split_message(message, max_length=2000):
    return [message[i:i+max_length] for i in range(0, len(message), max_length)]

# Global DM blocker
@bot.check
async def block_dms(ctx):
    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("🙅‍♂️ Sorry, I don’t respond to DMs. Try using me in a server!")
        return False
    return True

# In-memory conversation history per user
conversation_histories = {}

# Probability command
@bot.command(name="probability", help="Returns a random probability (0–100%) for the given sentence.")
async def probability(ctx, *, sentence: str):
    norm = normalize(sentence)
    result = round(random.uniform(0, 100), 2)
    await ctx.send(f"🔍 Probability for: \"{norm}\"\n🎯 Result: **{result:.2f}%**")

# General-purpose AI command
@bot.command(name="joe", help="Ask anything – AI will respond intelligently.")
async def joe(ctx, *, question: str):
    try:
        completion = client.chat.completions.create(
            model="deepseek/deepseek-chat:free",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful, emotionally expressive assistant. "
                        "Respond clearly, helpfully, and naturally — feel free to use emojis to show tone and emotion. 😊👍 "
                        "Provide links to sources when relevant."
                    )
                },
                {"role": "user", "content": question}
            ],
            temperature=0.75
        )
        reply = completion.choices[0].message.content.strip()

        for chunk in split_message(reply):
            await ctx.send(chunk)

    except Exception as e:
        await ctx.send("⚠️ Mini Aoruen Crashed The Car. Try again shortly.")
        print(f"[AI Error] {e}")

# Meme command (Reddit)
@bot.command(name="meme", help="Fetch a meme from r/memes.")
async def meme(ctx):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://www.reddit.com/r/memes/top.json?limit=50&t=day",
            headers={"User-Agent": "trader-joe-bot"}
        ) as response:
            if response.status != 200:
                await ctx.send("😕 Failed to fetch memes from Reddit.")
                return
            data = await response.json()
            posts = data["data"]["children"]
            random.shuffle(posts)
            for post in posts:
                image_url = post["data"].get("url_overridden_by_dest")
                if image_url and image_url.endswith((".jpg", ".png", ".gif")):
                    await ctx.send(image_url)
                    return
            await ctx.send("⚠️ No image memes found!")

# Help command
@bot.command(name="help", help="List all available commands.")
async def help_command(ctx):
    help_text = (
        "🛠 **Available Commands:**\n"
        "• `!probability <sentence>` – Get a random probability score for your sentence.\n"
        "• `!joe <question>` – Ask the AI anything you want.\n"
        "• `!meme` – Grab a fresh meme from Reddit!\n"
        "• `!trivia` – Test your knowledge with a trivia question.\n"
        "• `!hangman start` / `!hangman guess <letter>` – Play Hangman together.\n"
        "• `!hack <username>` – Simulate a fake hacker mode.\n"
        "• `!help` – Show this help message. 😊"
    )
    await ctx.send(help_text)

# Bot ready event
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} — Ready on {len(bot.guilds)} servers.")

# --- New Features Added Below ---

# 1. Hangman Game Setup
class HangmanGame:
    MAX_WRONG = 6

    def __init__(self, word):
        self.word = word.lower()
        self.guessed = set()
        self.wrong_guesses = 0

    def display(self):
        displayed = " ".join(c if c in self.guessed else "_" for c in self.word)
        return f"`{displayed}`"

    def guess(self, letter):
        letter = letter.lower()
        if letter in self.guessed:
            return False, "You already guessed that letter."
        self.guessed.add(letter)
        if letter not in self.word:
            self.wrong_guesses += 1
            if self.wrong_guesses >= self.MAX_WRONG:
                return True, "lost"
            return True, "wrong"
        if all(c in self.guessed for c in self.word):
            return True, "won"
        return True, "correct"

hangman_games = {}

@bot.command(name="hangman", help="Start or play Hangman: `!hangman start` or `!hangman guess <letter>`.")
async def hangman(ctx, action=None, guess=None):
    channel_id = ctx.channel.id
    if action == "start":
        if channel_id in hangman_games:
            await ctx.send("⚠️ A game is already running in this channel.")
            return
        words = ["discord", "python", "bot", "openai", "hangman", "asyncio"]
        word = random.choice(words)
        hangman_games[channel_id] = HangmanGame(word)
        await ctx.send(f"🎉 Hangman started! Guess letters with `!hangman guess <letter>`.\n{hangman_games[channel_id].display()}")
    elif action == "guess":
        if channel_id not in hangman_games:
            await ctx.send("⚠️ No active game. Start one with `!hangman start`.")
            return
        if not guess or len(guess) != 1 or not guess.isalpha():
            await ctx.send("⚠️ Please guess a single letter: `!hangman guess <letter>`.")
            return
        game = hangman_games[channel_id]
        valid, result = game.guess(guess)
        if not valid:
            await ctx.send(result)  # Already guessed message
            return
        if result == "won":
            await ctx.send(f"🎉 You won! The word was **{game.word}**.")
            del hangman_games[channel_id]
        elif result == "lost":
            await ctx.send(f"💀 You lost! The word was **{game.word}**.")
            del hangman_games[channel_id]
        elif result == "wrong":
            await ctx.send(f"❌ Wrong guess! {game.display()} (Wrong guesses: {game.wrong_guesses}/{game.MAX_WRONG})")
        else:
            await ctx.send(f"✅ Good guess! {game.display()}")
    else:
        await ctx.send("Usage: `!hangman start` to begin or `!hangman guess <letter>` to guess.")

# 2. Trivia Command (Open Trivia DB)
@bot.command(name="trivia", help="Fetch a fresh trivia question from Open Trivia DB.")
async def trivia(ctx):
    async with aiohttp.ClientSession() as session:
        url = "https://opentdb.com/api.php?amount=1&type=multiple"
        async with session.get(url) as resp:
            if resp.status != 200:
                await ctx.send("⚠️ Failed to fetch trivia question.")
                return
            data = await resp.json()
            if data["response_code"] != 0 or not data["results"]:
                await ctx.send("⚠️ No trivia questions found.")
                return

            q = data["results"][0]
            question = re.sub(r"&quot;|&#039;", "'", q["question"])  # Basic HTML unescape
            correct_answer = re.sub(r"&quot;|&#039;", "'", q["correct_answer"])
            options = [re.sub(r"&quot;|&#039;", "'", opt) for opt in q["incorrect_answers"]] + [correct_answer]
            random.shuffle(options)

            def format_options(opts):
                return "\n".join(f"{chr(65+i)}. {opt}" for i, opt in enumerate(opts))

            await ctx.send(f"❓ Trivia: {question}\n{format_options(options)}\nReply with the letter of your answer within 15 seconds.")

            def check(m):
                return (
                    m.channel == ctx.channel and
                    m.author == ctx.author and
                    m.content.upper() in [chr(65+i) for i in range(len(options))]
                )

            try:
                msg = await bot.wait_for("message", timeout=15.0, check=check)
            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Time's up! The correct answer was **{correct_answer}**.")
                return

            selected = options[ord(msg.content.upper()) - 65]
            if selected == correct_answer:
                await ctx.send("✅ Correct! 🎉")
            else:
                await ctx.send(f"❌ Wrong! The correct answer was **{correct_answer}**.")

# 3. Fake Hacker Mode
FAKE_LOGS = [
    "Accessing mainframe...",
    "Bypassing firewall...",
    "Injecting malware...",
    "Extracting data...",
    "Spoofing IP address...",
    "Overriding security protocols...",
    "Decrypting passwords...",
    "Uploading ransomware...",
    "Launching DDoS attack...",
    "Compiling exploit...",
]

@bot.command(name="hack", help="Simulate a fake hacker attack on a username.")
async def hack(ctx, username: str = None):
    if not username:
        await ctx.send("Usage: `!hack <username>`")
        return
    await ctx.send(f"Initiating hack on **{username}**...")

    for _ in range(5):
        log = random.choice(FAKE_LOGS)
        await asyncio.sleep(1.5)
        await ctx.send(f"`{log}`")

    password = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
    await ctx.send(f"💾 Password found: **{password}** 🔓")
    await ctx.send(f"✅ Hack complete on **{username}**! (Totally fake, don’t worry 😉)")

# Minimal Flask Web Server to satisfy Render
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Start web server in background thread
threading.Thread(target=run_web).start()

# Start the bot
bot.run(TOKEN)
