import os
import discord
import logging

from discord.ext import commands
from dotenv import load_dotenv
from chatgpt_bot import get_chatgpt_response
from chatgpt_stream import chatgpt_stream_response
from text_to_voice import generate_and_stream_to_discord

PREFIX = "!"

# Setup logging
logger = logging.getLogger("discord")

# TODO: change this if deploying on cloud
if not discord.opus.is_loaded():
    print("Opus is not loaded! Trying to load it manually...")
    discord.opus.load_opus("/opt/homebrew/Cellar/opus/1.5.2/lib/libopus.dylib")

# Load the environment variables
load_dotenv()

# Get the token and print it for debugging
token = os.getenv("DISCORD_TOKEN")
print("Loaded Discord token:", token)  # Debug print

# Create the bot with all intents
# The message content and members intent must be enabled in the Discord Developer Portal for the bot to work.
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    """
    Called when the client is done preparing the data received from Discord.
    Prints message on terminal when bot successfully connects to discord.

    https://discordpy.readthedocs.io/en/latest/api.html#discord.on_ready
    """
    logger.info(f"{bot.user} has connected to Discord!")


@bot.event
async def on_message(message: discord.Message):
    """
    Called when a message is sent in any channel the bot can see.

    https://discordpy.readthedocs.io/en/latest/api.html#discord.on_message
    """
    # Don't delete this line! It's necessary for the bot to process commands.
    await bot.process_commands(message)

    # Ignore messages from self or other bots to prevent infinite loops.
    if message.author.bot or message.content.startswith("!"):
        return

    # Process the message with ChatGPT
    logger.info(f"Processing message from {message.author}: {message.content}")
    
    # check if the bot is in a voice channel, speak response if it is
    if message.guild and message.guild.voice_client:
        response = get_chatgpt_response(message.content)
        await generate_and_stream_to_discord(response, message.guild.voice_client)
    else:
        response = get_chatgpt_response(message.content)
        await message.reply(response)


# Commands


# This example command is here to show you how to add commands to the bot.
# Run !ping with any number of arguments to see the command in action.
# Feel free to delete this if your project will not need commands.
@bot.command(name="ping", help="Pings the bot.")
async def ping(ctx, *, arg=None):
    if arg is None:
        await ctx.send("Pong!")
    else:
        await ctx.send(f"Pong! Your argument was {arg}")


@bot.command(name='ask')
async def ask(ctx, *, question):
    """Get a response from ChatGPT"""
    response = get_chatgpt_response(question)
    await ctx.send(response)

@bot.command(name='askstream')
async def askstream(ctx, *, question):
    """Get a streaming response from ChatGPT"""
    message = await ctx.send("Thinking...")
    try:
        # Get the streaming response and update message periodically
        current_response = ""
        async for chunk in chatgpt_stream_response(question):
            current_response += chunk
            if len(current_response) % 100 == 0:  # Update every ~100 characters
                await message.edit(content=current_response)
        
        # Final update with complete response
        await message.edit(content=current_response)
    except Exception as e:
        await message.edit(content=f"Error: {str(e)}")

@bot.command(name='join')
async def join(ctx):
    """Join the user's voice channel"""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f'Joined {channel.name}')
    else:
        await ctx.send('You need to be in a voice channel first!')


@bot.command(name='leave')
async def leave(ctx):
    """Leave the voice channel"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send('Left the voice channel')
    else:
        await ctx.send('I am not in a voice channel')

# Start the bot, connecting it to the gateway
bot.run(token)
