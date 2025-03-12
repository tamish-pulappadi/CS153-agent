import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from chatgpt_bot import get_chatgpt_response
from chatgpt_stream import chatgpt_stream_response
from text_to_voice import generate_and_stream_to_discord
import logging
import asyncio
import websockets
import json
from deepgram import Deepgram
import requests
import audioop

# Load environment variables
load_dotenv()

PREFIX = "!"

# Setup logging
logger = logging.getLogger("discord")

# TODO: change this if deploying on cloud
if not discord.opus.is_loaded():
    print("Opus is not loaded! Trying to load it manually...")
    discord.opus.load_opus("/opt/homebrew/Cellar/opus/1.5.2/lib/libopus.dylib")

# Get the token and print it for debugging
token = os.getenv("DISCORD_TOKEN")
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')

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
        #response = get_chatgpt_response(message.content)
        await generate_and_stream_to_discord(message.content, message.guild.voice_client)
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
        await ctx.send("❌ You need to be in a voice channel first.")

# Join VC Command
@bot.command(name='joinvc')
async def joinvc(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        vc = await channel.connect()
        await ctx.send(f"✅ Joined {channel}!")
        asyncio.create_task(handle_audio(vc))  # Start audio handler
    else:
        await ctx.send("❌ You need to be in a voice channel first.")

# Leave VC Command
@bot.command(name='leavevc')
async def leavevc(ctx):
    vc = ctx.voice_client
    if vc:
        await vc.disconnect()
        await ctx.send("👋 Left the voice channel.")
    else:
        await ctx.send("❌ I'm not connected to a voice channel.")

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

# Handle Audio Streaming
async def handle_audio(vc):
    receiver = discord.reader.AudioReceiver()  # need to create an audio receiver

    # Connect to Deepgram WebSocket
    dg_client = Deepgram(DEEPGRAM_API_KEY)

    deepgram_socket = await dg_client.transcription.live({
        'punctuate': True,
        'interim_results': False,
        'language': 'en-US'
    })

    # Listen for Deepgram responses
    async def handle_transcripts():
        async for message in deepgram_socket:
            transcript = message.get('channel', {}).get('alternatives', [{}])[0].get('transcript')
            if transcript:
                print(f"📝 Transcript: {transcript}")
                send_to_api(transcript)

    asyncio.create_task(handle_transcripts())

    # Continuously send audio packets to Deepgram
    while vc.is_connected():
        audio_packet = await receiver.read()  #need to fix
        if audio_packet:
            pcm_data = decode_audio(audio_packet)
            await deepgram_socket.send(pcm_data)

# Decode Opus to PCM for Deepgram
def decode_audio(packet):
    pcm = audioop.lin2lin(packet, 2, 2)  # Conceptual. still figuring out how to do this in discord.py since can't stream audio with py
    return pcm

# Send transcript to your real-time API
def send_to_api(transcript):
    url = 'https://your-api.com/endpoint'  # Replace with our endpoint
    payload = {'message': transcript}
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            print("✅ Transcript sent successfully!")
        else:
            print(f"❌ Failed to send transcript. Status: {response.status_code}")
    except Exception as e:
        print(f"❌ Error sending transcript: {e}")

# Start the bot, connecting it to the gateway
bot.run(token)
