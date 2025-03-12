import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
from flask import Flask, request, jsonify
import threading
from datetime import datetime
import json
from deepgram import Deepgram
import wave
import logging
from chatgpt_bot import get_chatgpt_response
from chatgpt_stream import chatgpt_stream_response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')

# Set up Discord bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Set up Flask app
app = Flask(__name__)

# Dictionary to store active transcription sessions
active_sessions = {}

class TranscriptionSession:
    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.transcripts = []
        self.start_time = datetime.now()
        self.is_active = True

    def add_transcript(self, user_id, text):
        self.transcripts.append({
            'user_id': user_id,
            'text': text,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })

# Flask route to receive transcriptions from Node.js
@app.route('/transcription', methods=['POST'])
def receive_transcription():
    data = request.json
    user_id = data.get('user')
    message = data.get('message')
    
    print(f"📝 Received from {user_id}: {message}")

    # generate response
    logger.info(f"📝 Received from {user_id}: {message}")
    
    # check if the bot is in a voice channel, speak response if it is
    if message:
        response = get_chatgpt_response(message)
        #response = "hi how are you"
        return jsonify({'response': response}), 200
    
    return jsonify({'response': ''}), 200

@bot.event
async def on_ready():
    print(f"🎤 {bot.user} is ready and online!")

@bot.command(name='joinvc')
async def joinvc(ctx):
    if not ctx.author.voice:
        return await ctx.send("❌ You need to be in a voice channel first.")
    
    try:
        channel = ctx.author.voice.channel
        session_id = f"{ctx.guild.id}_{channel.id}"
        
        # Create new transcription session
        active_sessions[session_id] = TranscriptionSession(channel.name)
        
        await ctx.send(f"✅ Tracking transcriptions in {channel.name}!")
        
    except Exception as e:
        print(f"Error in joinvc: {e}")
        await ctx.send(f"❌ Error starting transcription session: {str(e)}")

async def save_transcript(ctx, session_id):
    session = active_sessions.get(session_id)
    if not session or not session.transcripts:
        await ctx.send("No transcripts to save!")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"transcripts/transcript_{timestamp}.txt"
    
    # Ensure transcripts directory exists
    os.makedirs('transcripts', exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Transcript from Discord Voice Channel: {session.channel_name}\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-" * 50 + "\n\n")
        
        for transcript in session.transcripts:
            user = await bot.fetch_user(int(transcript['user_id']))
            username = user.name if user else transcript['user_id']
            f.write(f"[{transcript['timestamp']}] {username}: {transcript['text']}\n")

    await ctx.send("📝 Here's your transcript:", file=discord.File(filename))

@bot.command(name='leavevc')
async def leavevc(ctx):
    session_id = f"{ctx.guild.id}_{ctx.author.voice.channel.id}"
    
    if session_id in active_sessions:
        active_sessions[session_id].is_active = False
        del active_sessions[session_id]
        await ctx.send("👋 Stopped tracking transcriptions. Transcript has been saved!")
    else:
        await ctx.send("❌ No active transcription session.")

@bot.command(name='status')
async def status(ctx):
    if not ctx.author.voice:
        return await ctx.send("❌ You're not in a voice channel.")

    session_id = f"{ctx.guild.id}_{ctx.author.voice.channel.id}"
    session = active_sessions.get(session_id)
    
    if not session:
        return await ctx.send("❌ No active recording session.")

    duration = (datetime.now() - session.start_time).seconds
    transcript_count = len(session.transcripts)
    
    await ctx.send(
        f"✅ Currently tracking transcriptions in {session.channel_name}\n"
        f"📝 {transcript_count} transcripts captured\n"
        f"⏱️ Session duration: {duration} seconds"
    )

@bot.command(name='savenow')
async def savenow(ctx):
    if not ctx.author.voice:
        return await ctx.send("❌ You're not in a voice channel.")

    session_id = f"{ctx.guild.id}_{ctx.author.voice.channel.id}"
    
    if session_id not in active_sessions:
        return await ctx.send("❌ No active transcription session.")

    try:
        await save_transcript(ctx, session_id)
        active_sessions[session_id].transcripts = []  # Clear transcripts but keep session active
        await ctx.send("💾 Transcript saved! Continuing to track transcriptions...")
    except Exception as e:
        await ctx.send(f"❌ Error saving transcript: {str(e)}")

@bot.command(name='helpme')
async def help(ctx):
    help_text = """
🎤 **Voice Transcription Bot Commands**
`!joinvc` - Start tracking transcriptions in your voice channel
`!leavevc` - Stop tracking and save transcript
`!status` - Check tracking status
`!savenow` - Save current transcript without stopping
`!help` - Show this help message
    """
    await ctx.send(help_text)

# Error handling
@bot.event
async def on_error(event, *args, **kwargs):
    print(f"Error in {event}:", args[0])

# Add new routes for status and save commands
@app.route('/transcription/status', methods=['POST'])
def check_status():
    data = request.json
    print(f"🔍 DEBUG: Received status request: {data}")
    
    guild_id = data.get('guild_id')
    channel_id = data.get('channel_id')
    session_id = f"{guild_id}_{channel_id}"
    
    if session_id in active_sessions:
        session = active_sessions[session_id]
        return {
            'status': 'active',
            'transcript_count': len(session.transcripts),
            'duration': (datetime.now() - session.start_time).seconds
        }
    return {'status': 'inactive'}, 404

@app.route('/transcription/save', methods=['POST'])
def save_now():
    data = request.json
    print(f"🔍 DEBUG: Received save request: {data}")
    
    guild_id = data.get('guild_id')
    channel_id = data.get('channel_id')
    session_id = f"{guild_id}_{channel_id}"
    
    if session_id in active_sessions:
        # Call save_transcript here
        # You'll need to modify save_transcript to work with the Flask context
        return {'status': 'saved'}
    return {'status': 'no_session'}, 404

def run_flask():
    app.run(port=5000)

def run_discord_bot():
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Run Discord bot in main thread
    #run_discord_bot()
