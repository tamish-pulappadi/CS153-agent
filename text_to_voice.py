import os
from typing import IO
import discord
import io
import asyncio

from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs


ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
client = ElevenLabs(
    api_key=ELEVENLABS_API_KEY,
)

async def generate_and_stream_to_discord(text: str, voice_client):
    # Generate the audio stream from text
    response = client.text_to_speech.convert(
        voice_id="19STyYD15bswVz51nqLf", # Adam pre-made voice
        output_format="mp3_22050_32",
        text=text,
        model_id="eleven_turbo_v2_5",
        # Optional voice settings that allow you to customize the output
        voice_settings=VoiceSettings(
            stability=0.0,
            similarity_boost=1.0,
            style=0.0,
            use_speaker_boost=True,
            speed=1.0,
        ),
    )
    
    # Create an audio source from the stream
    buffer = io.BytesIO()
    for chunk in response:
        if chunk:
            buffer.write(chunk)
    
    buffer.seek(0)
    audio_source = discord.FFmpegPCMAudio(buffer, pipe=True)
    
    # Play the audio
    if not voice_client.is_playing():
        voice_client.play(audio_source)
    else:
        # Queue the audio or handle concurrent requests as needed
        await asyncio.sleep(0.5)  # Wait a bit for current audio to finish
        voice_client.play(audio_source)
