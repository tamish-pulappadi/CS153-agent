import discord
from dotenv import load_dotenv
import os

# Load token from .env
load_dotenv()
token = os.getenv('DISCORD_TOKEN')
print(f"Full Discord token: {token}")  # Print the complete token for debugging

# Create client
intents = discord.Intents.all()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Successfully connected to Discord as {client.user}')
    print(f'Bot is in {len(client.guilds)} servers:')
    for guild in client.guilds:
        print(f'- {guild.name} (id: {guild.id})')
    await client.close()  # Close connection after successful test

@client.event
async def on_error(event, *args, **kwargs):
    print(f'An error occurred: {event}')
    await client.close()

try:
    print('Attempting to connect to Discord...')
    client.run(token)
    print('Test completed successfully!')
except Exception as e:
    print(f'Error occurred: {str(e)}') 