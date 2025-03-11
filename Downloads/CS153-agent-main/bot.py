import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import json
from deepgram import Deepgram
import wave
import datetime

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Dictionary to store transcripts for each session
transcripts = {}

@bot.event
async def on_ready():
    print(f"🎤 {bot.user} is ready and online!")

@bot.command(name='status')
async def status(ctx):
    """Check if the bot is recording in the current channel"""
    if ctx.voice_client:
        session_id = str(ctx.guild.id) + "_" + str(ctx.voice_client.channel.id)
        if session_id in transcripts:
            transcript_count = len(transcripts[session_id])
            await ctx.send(f"✅ Currently recording in {ctx.voice_client.channel.name}. {transcript_count} transcripts captured.")
        else:
            await ctx.send("❌ Connected but not recording.")
    else:
        await ctx.send("❌ Not connected to any voice channel.")

@bot.command(name='savenow')
async def savenow(ctx):
    """Save the current transcript without leaving the channel"""
    if ctx.voice_client:
        session_id = str(ctx.guild.id) + "_" + str(ctx.voice_client.channel.id)
        if session_id in transcripts:
            await save_transcript(ctx, session_id)
            # Clear the transcripts but keep recording
            transcripts[session_id] = []
            await ctx.send("💾 Transcript saved! Continuing to record...")
        else:
            await ctx.send("❌ No transcripts to save.")
    else:
        await ctx.send("❌ Not connected to any voice channel.")

@bot.command(name='help')
async def help(ctx):
    """Show available commands"""
    commands = """
🎤 **Voice Transcription Bot Commands**
`!joinvc` - Join your voice channel and start recording
`!leavevc` - Leave voice channel and save transcript
`!status` - Check if bot is recording
`!savenow` - Save current transcript without stopping
`!help` - Show this help message
    """
    await ctx.send(commands)

# Join VC Command
@bot.command(name='joinvc')
async def joinvc(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        try:
            vc = await channel.connect()
            # Initialize empty transcript for this session
            session_id = str(ctx.guild.id) + "_" + str(channel.id)
            transcripts[session_id] = []
            
            await ctx.send(f"✅ Joined {channel}! Recording and transcribing...")
            asyncio.create_task(handle_audio(vc, ctx, session_id))
        except Exception as e:
            await ctx.send(f"❌ Error joining voice channel: {str(e)}")
    else:
        await ctx.send("❌ You need to be in a voice channel first.")

# Leave VC Command
@bot.command(name='leavevc')
async def leavevc(ctx):
    if ctx.voice_client:
        session_id = str(ctx.guild.id) + "_" + str(ctx.voice_client.channel.id)
        
        # Save transcript before disconnecting
        if session_id in transcripts:
            await save_transcript(ctx, session_id)
            del transcripts[session_id]
        
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Left the voice channel. Transcript has been saved!")
    else:
        await ctx.send("❌ I'm not connected to a voice channel.")

async def save_transcript(ctx, session_id):
    if not transcripts[session_id]:
        await ctx.send("No transcripts to save!")
        return
        
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"transcript_{timestamp}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Transcript from Discord Voice Channel: {ctx.voice_client.channel.name}\n")
        f.write(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-" * 50 + "\n\n")
        for transcript in transcripts[session_id]:
            f.write(f"{transcript}\n")
    
    # Send the transcript file to Discord
    await ctx.send("📝 Here's your transcript:", file=discord.File(filename))

async def handle_audio(vc, ctx, session_id):
    # Connect to Deepgram WebSocket
    dg_client = Deepgram(DEEPGRAM_API_KEY)
    
    try:
        deepgram_socket = await dg_client.transcription.live({
            'punctuate': True,
            'interim_results': False,
            'language': 'en-US',
            'model': 'general',
            'encoding': 'linear16',
            'sample_rate': 48000
        })

        # Listen for Deepgram responses
        @deepgram_socket.event
        async def on_transcript(transcript):
            transcript_text = transcript['channel']['alternatives'][0].get('transcript', '')
            if transcript_text.strip():
                # Store the transcript
                transcripts[session_id].append(transcript_text)
                # Print to console for debugging
                print(f"🎤 Transcribed: {transcript_text}")
        
        # Start recording
        vc.start_recording(
            discord.sinks.WaveSink(),
            once_done,
            ctx
        )
        
        # Keep the connection alive while recording
        while vc.is_connected():
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"Error in handle_audio: {str(e)}")
        await ctx.send(f"❌ Error during transcription: {str(e)}")
    finally:
        if vc.is_connected():
            vc.stop_recording()
            await deepgram_socket.finish()

async def once_done(sink: discord.sinks.WaveSink, ctx: commands.Context):
    # Convert the recorded audio to the format Deepgram expects
    for user_id, audio in sink.audio_data.items():
        # Send audio data to Deepgram
        if audio.file:
            try:
                with wave.open(audio.file, 'rb') as wave_file:
                    audio_data = wave_file.readframes(wave_file.getnframes())
                    await deepgram_socket.send(audio_data)
            except Exception as e:
                print(f"Error processing audio: {str(e)}")

# Start bot
bot.run(DISCORD_TOKEN)
