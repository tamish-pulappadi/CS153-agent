import dotenv from 'dotenv';
import { Client, GatewayIntentBits } from 'discord.js';
import { 
    joinVoiceChannel,
    EndBehaviorType,
    VoiceReceiver,
    createAudioResource,
    getVoiceConnection,
    createAudioPlayer
} from '@discordjs/voice';
import prism, { opus } from 'prism-media';
import fetch from 'node-fetch';
import { Readable } from 'stream';

import { AssemblyAI } from "assemblyai";
import { ElevenLabsClient } from "elevenlabs";

// Initialize dotenv
dotenv.config();

// Environment variables
const ASSEMBLYAI_API_KEY = process.env.ASSEMBLYAI_API_KEY;
const DISCORD_TOKEN = process.env.DISCORD_TOKEN;
const ELEVENLABS_API_KEY = process.env.ELEVENLABS_API_KEY;

const assemblyAI = new AssemblyAI({ apiKey: ASSEMBLYAI_API_KEY });
const elevenLabs = new ElevenLabsClient({ apiKey: ELEVENLABS_API_KEY });

const player = createAudioPlayer();

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

    if (command === '!join') {
        await handleJoinVC(message);
    } else if (command === '!leave') {
        await handleLeaveVC(message);
    } else if (command === '!help') {
        message.reply('🎤 **Eva, your personal assistanct -- Bot Commands**\n`!join` - Start assistance in your voice channel\n`!leave` - Stop assistance and leave channel and save transcript\n`!help` - Show this help message');
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
            selfMute: false
        });

        // Get the voice receiver
        const receiver = connection.receiver;
        
        // Store connection info
        activeConnections.set(guildId, {
            connection,
            receiver,
            channel: channel
        });

        // Set up speaking event to handle only one user at a time
        let currentlySpeakingUsers = new Set();
        receiver.speaking.on('start', (userId) => {
            if (currentlySpeakingUsers.has(userId)) {
                console.log(`🚫 User ${userId} tried to speak again, but they are already speaking.`);
                return;
            }
            console.log(`🎙️ User ${userId} started speaking`);
            currentlySpeakingUsers.add(userId);
            handleUserAudio(connection, userId, guildId);
        });
        receiver.speaking.on('end', (userId) => {
            if (currentlySpeakingUsers.has(userId)) {
                console.log(`🚫 User ${userId} stopped speaking.`);
                currentlySpeakingUsers.delete(userId);
            }
        });

        console.log(`🎤 Joined VC: ${channel.name}`);
        message.reply(`✅ Joined ${channel.name} and capturing audio!`);

    } catch (error) {
        console.error('Error joining voice channel:', error);
        message.reply(`❌ Error joining voice channel: ${error.message}`);
    }
}

async function handleUserAudio(connection, userId, guildId) {
    const receiver = connection.receiver;

    // Set up the real-time transcriber
    const transcriber = assemblyAI.realtime.transcriber({
        sampleRate: 48000, // Match the sample rate used in Discord audio
       });
    
    await transcriber.connect();

    transcriber.on('open', ({ sessionId }) => {
        console.log(`Real-time session opened with ID: ${sessionId}`);
      });
    
    transcriber.on('error', (error) => {
    console.error('Real-time transcription error:', error);
    });

    transcriber.on('close', (code, reason) => {
    console.log('Real-time session closed:', code, reason);
    });

    var transcription =""
    transcriber.on('transcript', (transcript) => {
    if (transcript.message_type === 'FinalTranscript') {
        transcription += transcript.text + " "; // Append to the full message
    }
    });

    // Create audio stream
    const audioStream = receiver.subscribe(userId, {
        end: {
            behavior: EndBehaviorType.AfterSilence,
            duration: 1000
        }
    });
    
    const opusDecoder = new prism.opus.Decoder({ rate: 48000, channels: 1 });
    
    // Pipe the decoded audio chunks to AssemblyAI for transcription
    audioStream.pipe(opusDecoder).on("data", (chunk) => {
        transcriber.sendAudio(chunk);
    });

    // Handle disconnection
    audioStream.on("end", async () => {
        await transcriber.close();
        // Send to python flask
        try {
            if (transcription) {
                console.log(`📝 Generating response for for ${userId}: ${transcription}`);
                const response = await sendTranscriptionToPython(userId, transcription);
                console.log(`Response received from Python: ${response}`);

                const audioStream = await elevenLabs.textToSpeech.convertAsStream("19STyYD15bswVz51nqLf", {
                    text: response.response,
                    model_id: "eleven_turbo_v2_5"
                });

                const resource = createAudioResource(Readable.from(audioStream));
                player.play(resource);

                //const audioSource = new discord.AudioResource(Readable.from(readableStream), { inlineVolume: true });
                //const player = voiceClient.play(audioSource);

                connection.subscribe(player);
                player.on('error', console.error);
                    
            }
        } catch (error) {
            console.error('Error processing transcription:', error);
        }
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

        const data = await response.json();
        console.log(`✅ Sent transcript to Python bot for user ${userId}. Response: ${JSON.stringify(data)}`);
        return data; // Return the response data
    } catch (error) {
        console.error('Error sending transcript to Python:', error);
        throw error; // Rethrow the error to handle it in the calling function
    }
}

// Error handling
client.on('error', console.error);
process.on('unhandledRejection', console.error);

// Login
client.login(DISCORD_TOKEN); 