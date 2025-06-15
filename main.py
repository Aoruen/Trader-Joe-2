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
import asyncpraw
import io
import PIL.Image
import PIL.ImageFilter
from urllib.parse import urlparse

# Environment Variables
TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "discord:trader-joe-bot:v1.0 (by /u/your_reddit_username)")

if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is missing!")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable is missing!")
if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
    raise ValueError("Reddit OAuth environment variables are missing!")

# OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# Async Reddit client
reddit = asyncpraw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT,
)

# Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# Helpers
def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())

def split_message(message, max_length=2000):
    return [message[i:i+max_length] for i in range(0, len(message), max_length)]

@bot.check
async def block_dms(ctx):
    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("🙅‍♂️ Sorry, I don’t respond to DMs. Try using me in a server!")
        return False
    return True

conversation_histories = {}

# Commands
@bot.command(name="probability", help="Returns a random probability (0–100%) for the given sentence.")
async def probability(ctx, *, sentence: str):
    norm = normalize(sentence)
    result = round(random.uniform(0, 100), 2)
    await ctx.send(f"🔍 Probability for: \"{norm}\"\n🎯 Result: **{result:.2f}%**")

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

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

@bot.command(name="redditroulette", help="Spin the Reddit wheel and Take a Chance.")
async def redditroulette(ctx):
    try:
        subreddit_names = ["FemBoys", "futanari"]
        chosen_subreddit = random.choice(subreddit_names)
        subreddit = await reddit.subreddit(chosen_subreddit)

        posts = []
        async for post in subreddit.hot(limit=1000):
            posts.append(post)
        if not posts:
            await ctx.send(f"⚠️ No posts found in r/{chosen_subreddit}!")
            return

        random.shuffle(posts)

        image_extensions = (".jpg", ".jpeg", ".png")  # images allowed for upload
        video_extensions = (".mp4", ".webm", ".gifv", ".gif")          # videos/gif replacements to link

        for post in posts:
            url = post.url
            lower_url = url.lower()
            parsed = urlparse(lower_url)
            filename = os.path.basename(parsed.path)

            # Check if post is a Reddit-hosted video
            if getattr(post, "is_video", False):
                # Get the reddit_video fallback url
                if post.media and "reddit_video" in post.media:
                    video_url = post.media["reddit_video"].get("fallback_url")
                    if video_url:
                        # Just send the video URL so it embeds and plays
                        await ctx.send(f"🎲 From r/{chosen_subreddit}: {post.title}\n{video_url}")
                        return
                continue  # skip if no fallback video url

            # If the url is a video type but not marked as reddit video (like gifv or webm)
            if filename.endswith(video_extensions):
                # Send URL directly to allow playback
                await ctx.send(f"🎲 From r/{chosen_subreddit}: {post.title}\n{url}")
                return

            # Else if url is an image type, or fallback preview image
            if filename.endswith(image_extensions):
                media_url = url
            else:
                # Try preview image fallback
                if hasattr(post, "preview") and "images" in post.preview:
                    images = post.preview["images"]
                    if images:
                        preview_url = images[0].get("source", {}).get("url", "").replace("&amp;", "&")
                        parsed_preview = urlparse(preview_url)
                        preview_filename = os.path.basename(parsed_preview.path)
                        if preview_filename.endswith(image_extensions):
                            media_url = preview_url
                            filename = preview_filename
                        else:
                            continue
                    else:
                        continue
                else:
                    continue

            # Download media data
            async with aiohttp.ClientSession() as session:
                async with session.get(media_url) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.read()

            if len(data) > MAX_FILE_SIZE:
                continue

            # Add spoiler prefix for images
            if chosen_subreddit.lower() in ["femboys", "futanari"]:
                filename = "SPOILER_" + filename

            file = discord.File(fp=io.BytesIO(data), filename=filename)
            await ctx.send(f"🎲 From r/{chosen_subreddit}: {post.title}", file=file)
            return

        await ctx.send(f"⚠️ Couldn't find any suitable media under 10MB in r/{chosen_subreddit} right now!")

    except Exception as e:
        await ctx.send("😕 Failed to fetch media from Reddit.")
        print(f"[Reddit Error] {e}")

@bot.command(name="help", help="List all available commands.")
async def help_command(ctx):
    help_text = (
        "🛠 **Available Commands:**\n"
        "• `!probability <sentence>` – Get a random probability score for your sentence.\n"
        "• `!joe <question>` – Ask the AI anything you want.\n"
        "• `!redditroulette` – Spin the Reddit wheel for a random image.\n"
        "• `!trivia` – Test your knowledge with a trivia question.\n"
        "• `!hangman start` / `!hangman guess <letter>` – Play Hangman together.\n"
        "• `!hack <username>` – Simulate a hacker mode.\n"
        "• `!8ball <Yes Or No Question>` -Ask The 8-Ball a question\n"
        "• `!coinflip` – Flip A Coin.\n"
        "• `!roll <Number of dice-Number of Sides Ex. 2D6>` – Roll The Dice.\n"
        "• `!filter <blur, contour, detail, sharpen, emboss>` – Applies a filter to a image of your choice.\n"
        "• `!help` – Show this help message. 😊"
    )
    await ctx.send(help_text)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} — Ready on {len(bot.guilds)} servers.")

# Hangman Game
class HangmanGame:
    MAX_WRONG = 6

    def __init__(self, word):
        self.word = word.lower()
        self.guessed = set()
        self.wrong_guesses = 0

    def display(self):
        return f"`{' '.join(c if c in self.guessed else '_' for c in self.word)}`"

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
            await ctx.send(result)
        elif result == "won":
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
        await ctx.send("Usage: `!hangman start` or `!hangman guess <letter>`.")

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
            question = re.sub(r"&quot;|&#039;", "'", q["question"])
            correct_answer = re.sub(r"&quot;|&#039;", "'", q["correct_answer"])
            options = [re.sub(r"&quot;|&#039;", "'", opt) for opt in q["incorrect_answers"]] + [correct_answer]
            random.shuffle(options)

            def format_options(opts):
                return "\n".join(f"{chr(65+i)}. {opt}" for i, opt in enumerate(opts))

            await ctx.send(f"❓ Trivia: {question}\n{format_options(options)}\nReply with the letter of your answer within 15 seconds.")

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author and m.content.upper() in [chr(65+i) for i in range(len(options))]

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
    await ctx.send(f"✅ Hack complete on **{username}**!")

@bot.command(name="8ball", help="Ask the magic 8 ball a question.")
async def magic_8ball(ctx, *, question: str):
    responses = [
        "It is certain.",
        "Without a doubt.",
        "You may rely on it.",
        "Yes, definitely.",
        "It is decidedly so.",
        "As I see it, yes.",
        "Most likely.",
        "Outlook good.",
        "Yes.",
        "Signs point to yes.",
        "Reply hazy, try again.",
        "Ask again later.",
        "Better not tell you now.",
        "Cannot predict now.",
        "Concentrate and ask again.",
        "Don't count on it.",
        "My reply is no.",
        "My sources say no.",
        "Outlook not so good.",
        "Very doubtful."
    ]
    answer = random.choice(responses)
    await ctx.send(f"🎱 Question: {question}\n🎱 Magic 8 Ball says: **{answer}**")

@bot.command(name="coinflip", help="Flip a coin.")
async def coinflip(ctx):
    result = random.choice(["Heads", "Tails"])
    await ctx.send(f"🪙 The coin landed on **{result}**!")

@bot.command(name="roll", help="Roll dice. Usage: !roll 2d6 (roll 2 six-sided dice).")
async def roll(ctx, dice: str):
    match = re.fullmatch(r"(\d*)d(\d+)", dice.lower())
    if not match:
        await ctx.send("⚠️ Invalid dice format. Use NdM, e.g., `2d6` or `d20`.")
        return

    count = int(match.group(1)) if match.group(1) else 1
    sides = int(match.group(2))
    if count > 100 or sides > 1000:
        await ctx.send("⚠️ That's too many dice or sides. Please keep it reasonable.")
        return

    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    rolls_str = ', '.join(str(r) for r in rolls)
    await ctx.send(f"🎲 Rolled {dice}: {rolls_str}\nTotal: **{total}**")

@bot.command(name="filter", help="Apply an image filter to an attached or replied-to image. Filters: blur, contour, detail, sharpen, emboss.")
async def filter_image(ctx, filter_name: str):
    filter_name = filter_name.lower()
    filters = {
        "blur": PIL.ImageFilter.BLUR,
        "contour": PIL.ImageFilter.CONTOUR,
        "detail": PIL.ImageFilter.DETAIL,
        "sharpen": PIL.ImageFilter.SHARPEN,
        "emboss": PIL.ImageFilter.EMBOSS
    }
    if filter_name not in filters:
        await ctx.send("⚠️ Unknown filter! Available: blur, contour, detail, sharpen, emboss.")
        return

    # Find image attachment from message or replied message
    image_url = None
    if ctx.message.attachments:
        image_url = ctx.message.attachments[0].url
    elif ctx.message.reference:
        ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if ref_msg.attachments:
            image_url = ref_msg.attachments[0].url

    if not image_url:
        await ctx.send("⚠️ Please attach an image or reply to an image to use this command.")
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    await ctx.send("⚠️ Couldn't download the image.")
                    return
                data = await resp.read()

        with PIL.Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img_filtered = img.filter(filters[filter_name])

            # Save to BytesIO
            img_byte_arr = io.BytesIO()
            img_filtered.save(img_byte_arr, format="JPEG")
            img_byte_arr.seek(0)

            await ctx.send(file=discord.File(fp=img_byte_arr, filename=f"filtered_{filter_name}.jpg"))
    except Exception as e:
        await ctx.send("⚠️ Something went wrong applying the filter.")
        print(f"[Filter Error] {e}")
        
# Flask server
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web).start()

# Start bot
bot.run(TOKEN)
