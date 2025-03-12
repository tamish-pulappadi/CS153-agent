import dotenv from 'dotenv';
import { Client, GatewayIntentBits } from 'discord.js';
import { 
    joinVoiceChannel,
    EndBehaviorType,
    VoiceReceiver,
    getVoiceConnection
} from '@discordjs/voice';
import prism from 'prism-media';
import WebSocket from 'ws';
import fetch from 'node-fetch';

// Initialize dotenv
dotenv.config();

// Environment variables
const DISCORD_TOKEN = process.env.DISCORD_TOKEN;
const GLADIA_API_KEY = process.env.GLADIA_API_KEY;

// Create Discord client
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent
    ]
});

// Store active connections
const activeConnections = new Map();

client.once('ready', () => {
    console.log(`✅ Voice capture bot logged in as ${client.user.tag}`);
});

// Listen for commands
client.on('messageCreate', async (message) => {
    if (!message.content.startsWith('!') || message.author.bot) return;

    const command = message.content.toLowerCase();

    if (command === '!joinvc') {
        await handleJoinVC(message);
    } else if (command === '!leavevc') {
        await handleLeaveVC(message);
    }
});

async function handleJoinVC(message) {
    if (!message.member.voice.channel) {
        return message.reply('❌ You need to be in a voice channel first.');
    }

    const channel = message.member.voice.channel;
    const guildId = message.guild.id;

    try {
        // Check if already connected
        if (activeConnections.has(guildId)) {
            return message.reply('❌ Already connected to a voice channel in this server.');
        }

        // Join the voice channel
        const connection = joinVoiceChannel({
            channelId: channel.id,
            guildId: guildId,
            adapterCreator: message.guild.voiceAdapterCreator,
            selfDeaf: false,
            selfMute: true
        });

        // Get the voice receiver
        const receiver = connection.receiver;
        
        // Store connection info
        activeConnections.set(guildId, {
            connection,
            receiver,
            channel: channel
        });

        // Set up speaking event
        connection.receiver.speaking.on('start', (userId) => {
            console.log(`🎙️ User ${userId} started speaking`);
            handleUserAudio(connection.receiver, userId, guildId);
        });

        console.log(`🎤 Joined VC: ${channel.name}`);
        message.reply(`✅ Joined ${channel.name} and capturing audio!`);

    } catch (error) {
        console.error('Error joining voice channel:', error);
        message.reply(`❌ Error joining voice channel: ${error.message}`);
    }
}

async function handleUserAudio(receiver, userId, guildId) {
    // Create audio stream
    const audioStream = receiver.subscribe(userId, {
        end: {
            behavior: EndBehaviorType.AfterSilence,
            duration: 1000
        }
    });

    // Create Opus decoder
    const decoder = new prism.opus.Decoder({
        rate: 16000,
        channels: 1,
        frameSize: 960
    });

    // Pipe audio through decoder
    audioStream.pipe(decoder);

    // Connect to Gladia WebSocket
    const ws = new WebSocket('wss://api.gladia.io/audio/text/audio-transcription', {
        headers: {
            'x-gladia-key': GLADIA_API_KEY
        }
    });

    ws.on('open', () => {
        console.log(`🔌 WebSocket connected for user ${userId}`);
        
        decoder.on('data', (chunk) => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(chunk);
            }
        });
    });

    ws.on('message', async (data) => {
        try {
            const response = JSON.parse(data);
            if (response.prediction && response.prediction.trim()) {
                console.log(`📝 Transcription for ${userId}: ${response.prediction}`);
                await sendTranscriptionToPython(userId, response.prediction);
            }
        } catch (error) {
            console.error('Error processing transcription:', error);
        }
    });

    ws.on('error', (error) => {
        console.error(`WebSocket error for ${userId}:`, error);
    });

    ws.on('close', () => {
        console.log(`WebSocket closed for ${userId}`);
    });

    audioStream.on('end', () => {
        ws.close();
        decoder.destroy();
    });
}

async function handleLeaveVC(message) {
    const guildId = message.guild.id;
    
    if (!activeConnections.has(guildId)) {
        return message.reply('❌ Not connected to any voice channel.');
    }

    try {
        const { connection } = activeConnections.get(guildId);
        connection.destroy();
        activeConnections.delete(guildId);
        message.reply('👋 Left the voice channel.');
    } catch (error) {
        console.error('Error leaving voice channel:', error);
        message.reply(`❌ Error leaving voice channel: ${error.message}`);
    }
}

async function sendTranscriptionToPython(userId, transcript) {
    try {
        const response = await fetch('http://localhost:5000/transcription', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user: userId,
                message: transcript
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        console.log(`✅ Sent transcript to Python bot for user ${userId}`);
    } catch (error) {
        console.error('Error sending transcript to Python:', error);
    }
}

// Error handling
client.on('error', console.error);
process.on('unhandledRejection', console.error);

// Login
client.login(DISCORD_TOKEN); 