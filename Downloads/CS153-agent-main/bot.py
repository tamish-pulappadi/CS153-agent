import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import websockets
import json
from deepgram import Deepgram
import requests
import audioop

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

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

# Start bot
bot.run(DISCORD_TOKEN)
