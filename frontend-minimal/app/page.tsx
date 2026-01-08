'use client';

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import AudioCapture from '@/components/audio-capture';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { User, Bot, Mic, MicOff, Power, PowerOff, X } from 'lucide-react';
import AudioCaptureMediaRecorder from '@/components/audio-capture-mediarecorder';
import { ToolOutput } from '@/components/tool-outputs/ToolOutput';
import type { ToolOutput as ToolOutputType } from '@/components/tool-outputs/types';
import { AudioPlaybackService } from '@/components/audio-playback';
import { motion, AnimatePresence } from 'framer-motion';

interface TextMessage {
  text: string;
  role: string;
}

// Add these message animation variants before the Home component
const messageVariants = {
  initial: { 
    opacity: 0, 
    y: 20,
    scale: 0.95
  },
  animate: { 
    opacity: 1, 
    y: 0,
    scale: 1,
    transition: {
      type: "spring",
      stiffness: 260,
      damping: 20
    }
  },
  exit: { 
    opacity: 0, 
    scale: 0.95,
    transition: { duration: 0.2 }
  }
};

const avatarVariants = {
  initial: { scale: 0 },
  animate: { 
    scale: 1,
    transition: {
      type: "spring",
      stiffness: 260,
      damping: 20,
      delay: 0.1
    }
  }
};

export default function Home() {
  const [status, setStatus] = useState('Disconnected');
  const [recording, setRecording] = useState(false);
  const [textOutputs, setTextOutputs] = useState<TextMessage[]>([]);
  const [toolUiOutput, setToolUiOutput] = useState<ToolOutputType | null>(null);
  const [currentTool, setCurrentTool] = useState<{name: string, content: string} | null>(null);
  const [waitingForTool, setWaitingForTool] = useState(false);
  const [wsKey, setWsKey] = useState(0);
  const [isThinking, setIsThinking] = useState(false);
  const [toolConfigs, setToolConfigs] = useState<any[]>([]);
  // Generate typing sound programmatically instead of using MP3
  const [audioContext] = useState(() => typeof window !== 'undefined' ? new (window.AudioContext || (window as any).webkitAudioContext)() : null);
  const typingSoundInterval = useRef<NodeJS.Timeout | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const displayedMessages = useRef<Set<string>>(new Set());
  const displayedTextContentIds = useRef<Set<string>>(new Set());
  const contentIdToStage = useRef<Record<string, string>>({});
  const pendingTexts = useRef<Record<string, TextMessage>>({});
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const playbackServiceRef = useRef<AudioPlaybackService | null>(null);

  // Debug-enhanced recording state setter
  const setRecordingWithDebug = useCallback((value: boolean) => {
    console.log(`[Recording State] Setting to ${value}. Triggered by:`, new Error().stack);
    setRecording(value);
  }, []);

  const connect = () => {
    if (wsRef.current) wsRef.current.close();
    const wsUrl = process.env.NEXT_PUBLIC_BACKEND_WS_URL || 'ws://34.227.79.69:8000/ws';
    console.log('Connecting to WebSocket:', wsUrl);
    wsRef.current = new WebSocket(wsUrl);
    setStatus('Connecting...');
    setWsKey(k => k + 1);
    
    wsRef.current.onopen = () => setStatus('Connected');
    wsRef.current.onclose = () => {
      setStatus('Disconnected');
      setRecordingWithDebug(false);
    };
    wsRef.current.onerror = () => setStatus('Error');
    wsRef.current.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data);
          console.log('[WS MESSAGE]', msg);
          
          if (msg.event) handleEventMessage(msg.event);
        } catch (e) {
          console.error('Error parsing message:', e);
        }
      }
    };
  };

  // Memoize handlers to prevent unnecessary re-renders
  const handleAudioError = useCallback((error: Error) => {
    console.error('[Audio Error]', error);
    setRecordingWithDebug(false);
  }, [setRecordingWithDebug]);

  const addMessage = useCallback((message: TextMessage) => {
    const messageKey = `${message.role}:${message.text}`;
    if (!displayedMessages.current.has(messageKey)) {
      console.log('[ADDING MESSAGE]', message);
      displayedMessages.current.add(messageKey);
      setTextOutputs(prev => [...prev, message]);
    } else {
      console.log('[SKIPPING DUPLICATE]', message);
    }
      }, []);

  // Function to generate a typing sound programmatically
  const playTypingBeep = useCallback(() => {
    if (!audioContext) return;
    
    try {
      // Create a short beep sound (like a keyboard click)
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      
      // Set frequency for a subtle click sound
      oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
      oscillator.frequency.exponentialRampToValueAtTime(400, audioContext.currentTime + 0.1);
      
      // Set volume envelope for a quick click
      gainNode.gain.setValueAtTime(0, audioContext.currentTime);
      gainNode.gain.linearRampToValueAtTime(0.1, audioContext.currentTime + 0.01);
      gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.1);
      
      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.1);
    } catch (err) {
      console.error('Error playing typing sound:', err);
    }
  }, [audioContext]);

  // Function to start looping the typing sound
  const startTypingSound = useCallback(() => {
    if (audioContext) {
      // Set up the interval to play the sound repeatedly
      typingSoundInterval.current = setInterval(() => {
        playTypingBeep();
      }, 1500); // Adjust interval as needed (current: 1.5 seconds)
    }
  }, [audioContext, playTypingBeep]);

  // Function to stop the typing sound
  const stopTypingSound = useCallback(() => {
    if (typingSoundInterval.current) {
      clearInterval(typingSoundInterval.current);
      typingSoundInterval.current = null;
    }
  }, []);

  // Clean up interval on unmount
  useEffect(() => {
    return () => {
      if (typingSoundInterval.current) {
        clearInterval(typingSoundInterval.current);
      }
    };
  }, []);

  const handleEventMessage = (event: any) => {
    console.log('[WS EVENT]', event);
    
    if (event.init) {
      // Store tool configurations
      setToolConfigs(event.init.toolConfigs);
      return;
    }
    
    if (event.contentStart && event.contentStart.type === 'TEXT') {
      const contentId = event.contentStart.contentId;
      let stage = 'FINAL';
      if (event.contentStart.additionalModelFields) {
        try {
          const fields = JSON.parse(event.contentStart.additionalModelFields);
          if (fields.generationStage) stage = fields.generationStage;
        } catch (e) {
          console.error('[TEXT STAGE ERROR]', e);
        }
      }
      if (contentId) {
        console.log('[TEXT STAGE]', contentId, stage);
        contentIdToStage.current[contentId] = stage;
      }
    } else if (event.contentStart && event.contentStart.type === 'TOOL') {
      console.log('[TOOL START]', event);
      setWaitingForTool(true);
    } else if (event.toolUse) {
      console.log('[TOOL USE]', event.toolUse);
      setWaitingForTool(true);
      const toolName = event.toolUse.toolName;
      
      // Find the tool configuration and get its short description
      const toolConfig = toolConfigs.find((t: any) => t.name === toolName);
      setCurrentTool({
        name: toolName || 'Unknown Tool',
        content: 'Processing...'
      });
    } else if (event.toolResult) {
      // Tool result received
      console.log('[TOOL RESULT FULL]', event.toolResult);
      try {
        const parsedContent = JSON.parse(event.toolResult.content);
        console.log('[TOOL RESULT PARSED]', parsedContent);
      } catch (e) {
        console.error('[TOOL RESULT PARSE ERROR]', e);
      }
      setWaitingForTool(false);
      setCurrentTool(prev => prev ? {
        ...prev,
        content: JSON.stringify(JSON.parse(event.toolResult.content), null, 2)
      } : null);
    } else if (event.toolUiOutput) {
      // Handle tool UI output
      console.log('[TOOL UI OUTPUT]', event.toolUiOutput);
      
      // Handle barge-in events
      if (event.toolUiOutput.type === 'barge_in') {
        console.log('[BARGE IN] Stopping audio playback');
        if (playbackServiceRef.current) {
          playbackServiceRef.current.stop();
        }
      }
      
      // Handle tool execution progress events
      if (event.toolUiOutput.type === 'tool_exec_progress') {
        const status = event.toolUiOutput.content.status;
        if (status === 'started') {
          startTypingSound();
        } else if (status === 'completed') {
          stopTypingSound();
        }
      }

      // Set the entire toolUiOutput object to preserve all fields (appName, props, etc)
      setToolUiOutput(event.toolUiOutput);
    } else if (event.contentEnd && event.contentEnd.type === 'TOOL') {
      // Tool usage ended
      console.log('[TOOL END]', event);
      setCurrentTool(null);
      setWaitingForTool(false);
    } else if (event.audioOutput) {
      // Stream audio chunk immediately
      const base64Audio = event.audioOutput.content;
      const audioBytes = base64ToArrayBuffer(base64Audio);
      if (playbackServiceRef.current) {
        playbackServiceRef.current.playPCM(audioBytes);
      }
      
      // If there's pending text for this contentId, show it
      const contentId = event.audioOutput.contentId || 'default';
      if (contentId && pendingTexts.current[contentId]) {
        const textMessage = pendingTexts.current[contentId];
        addMessage(textMessage);
        displayedTextContentIds.current.add(contentId);
        delete pendingTexts.current[contentId];
      }
    } else if (event.textOutput) {
      const text = event.textOutput.content;
      const role = event.textOutput.role || 'ASSISTANT';
      const contentId = event.textOutput.contentId;
      
      console.log('[TEXT EVENT]', {
        text,
        role,
        contentId,
        hasContentId: !!contentId,
        isDisplayed: displayedTextContentIds.current.has(contentId),
      });

      // Skip empty messages
      if (!text || text.trim() === '') {
        return;
      }

      // Show text immediately for USER and SYSTEM roles
      if (role === 'USER' || role === 'SYSTEM') {
        console.log('[SHOWING USER/SYSTEM TEXT]', { text, role });
        addMessage({ text, role });
        if (contentId) displayedTextContentIds.current.add(contentId);
      } else if (role === 'ASSISTANT') {
        // For assistant messages, check if we have corresponding audio
        const hasAudioOutput = event.audioOutput && event.audioOutput.contentId === contentId;
        
        // Show text immediately if no audio is expected
        if (!contentId || !hasAudioOutput) {
          console.log('[SHOWING ASSISTANT TEXT IMMEDIATELY]', { text, role });
          addMessage({ text, role });
          if (contentId) displayedTextContentIds.current.add(contentId);
        } else {
          // Buffer the text to sync with audio
          console.log('[BUFFERING ASSISTANT TEXT]', { text, contentId });
          pendingTexts.current[contentId] = { text, role };
        }
      }
    }
  };

  const disconnect = useCallback(() => {
    console.log('[Disconnect] Cleaning up connection');
    setRecordingWithDebug(false);
    setStatus('Disconnected');
    setTextOutputs([]);
    displayedMessages.current.clear();
    displayedTextContentIds.current.clear();
    contentIdToStage.current = {};
    pendingTexts.current = {};
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
      setWsKey(k => k + 1);
    }
    if (playbackServiceRef.current) {
      playbackServiceRef.current.stop();
    }
  }, [setRecordingWithDebug]);

  const startRecording = useCallback(() => {
    console.log('[Start Recording]');
    setRecordingWithDebug(true);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send('start_audio');
    }
  }, [setRecordingWithDebug]);

  const stopRecording = useCallback(() => {
    console.log('[Stop Recording]');
    setRecordingWithDebug(false);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send('stop_audio');
    }
  }, [setRecordingWithDebug]);

  // Memoize audio capture components
  const audioCaptureComponent = useMemo(() => (
    <AudioCapture
      key={wsKey}
      websocket={wsRef.current}
      isCapturing={recording}
      onError={handleAudioError}
      inline
      setIsThinking={setIsThinking}
    />
  ), [wsKey, recording, handleAudioError, setIsThinking]);

  const audioMediaRecorderComponent = useMemo(() => (
    <AudioCaptureMediaRecorder
      websocket={wsRef.current}
      isCapturing={recording}
      onError={handleAudioError}
      inline
      setIsThinking={setIsThinking}
      promptName={wsRef.current ? 'user_audio_prompt' : 'inactive_prompt'}
      contentName={wsRef.current ? `user_audio_${Date.now()}` : 'inactive_content'}
    />
  ), [wsKey, recording, handleAudioError, setIsThinking]);

  const base64LPCM = (base64String: string): string => {
    const byteCharacters = atob(base64String);
    const byteArrays = new Uint8Array(byteCharacters.length);
    
    for (let i = 0; i < byteCharacters.length; i++) {
      byteArrays[i] = byteCharacters.charCodeAt(i);
    }

    const sampleRate = 24000;
    const numChannels = 1;
    const bitsPerSample = 16;
    const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
    const blockAlign = numChannels * (bitsPerSample / 8);
    const wavSize = byteArrays.length + 36;
    
    const wavHeader = new Uint8Array(44);
    const view = new DataView(wavHeader.buffer);

    let offset = 0;
    for (let i = 0; i < 4; i++) view.setUint8(offset++, "RIFF".charCodeAt(i));
    view.setUint32(offset, wavSize, true); offset += 4;
    for (let i = 0; i < 4; i++) view.setUint8(offset++, "WAVE".charCodeAt(i));
    for (let i = 0; i < 4; i++) view.setUint8(offset++, "fmt ".charCodeAt(i));
    view.setUint32(offset, 16, true); offset += 4;
    view.setUint16(offset, 1, true); offset += 2;
    view.setUint16(offset, numChannels, true); offset += 2;
    view.setUint32(offset, sampleRate, true); offset += 4;
    view.setUint32(offset, byteRate, true); offset += 4;
    view.setUint16(offset, blockAlign, true); offset += 2;
    view.setUint16(offset, bitsPerSample, true); offset += 2;
    for (let i = 0; i < 4; i++) view.setUint8(offset++, "data".charCodeAt(i));
    view.setUint32(offset, byteArrays.length, true); offset += 4;

    const wavBlob = new Blob([wavHeader, byteArrays], { type: "audio/wav" });
    return URL.createObjectURL(wavBlob);
  };

  // Helper function to convert base64 to ArrayBuffer
  const base64ToArrayBuffer = (base64: string): ArrayBuffer => {
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
  };

  useEffect(() => {
    if (!playbackServiceRef.current) {
      playbackServiceRef.current = new AudioPlaybackService();
    }

    return () => {
      if (playbackServiceRef.current) {
        playbackServiceRef.current.stop();
      }
    };
  }, []);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Add effect to log toolUiOutput state changes
  useEffect(() => {
    console.log('[TOOL UI OUTPUT STATE]', toolUiOutput);
  }, [toolUiOutput]);

  // Add clearToolOutput function
  const clearToolOutput = useCallback(() => {
    console.log('[CLEARING TOOL UI OUTPUT] by user');
    setToolUiOutput(null);
  }, []);

  // Add useEffect for auto-scrolling
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [textOutputs]); // Scroll when messages change

  const playTypingSound = useCallback(() => {
    playTypingBeep();
  }, [playTypingBeep]);

  return (
    <main className="min-h-screen h-screen flex flex-col items-center justify-center bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 p-6">
      {/* Tool Output Modal/Overlay */}
      {toolUiOutput && (
        <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-50 flex items-center justify-center p-6">
          <div className="bg-gradient-to-br from-blue-50/95 to-indigo-50/95 backdrop-blur-md rounded-3xl p-8 shadow-2xl border border-blue-200/50 max-w-4xl w-full max-h-[80vh] overflow-y-auto">
            <div className="flex justify-end mb-4">
              <Button
                onClick={clearToolOutput}
                variant="ghost"
                size="icon"
                className="h-10 w-10 rounded-2xl hover:bg-blue-100/80 transition-all duration-200 hover:scale-105"
              >
                <X size={18} className="text-blue-600" />
              </Button>
            </div>
            <ToolOutput output={toolUiOutput as ToolOutputType} websocket={wsRef.current} />
          </div>
        </div>
      )}

      {/* Waiting for Tool Overlay */}
      {waitingForTool && !toolUiOutput && (
        <div className="fixed inset-0 bg-blue-50/30 backdrop-blur-sm z-40 flex items-center justify-center">
          <div className="bg-gradient-to-br from-blue-100/90 to-indigo-100/90 backdrop-blur-md rounded-3xl p-12 shadow-xl border border-blue-200/50">
            <div className="flex flex-col items-center gap-6">
              <div className="relative">
                <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-500" />
                <div className="absolute inset-0 rounded-full bg-gradient-to-r from-blue-500/20 to-indigo-500/20 animate-pulse" />
              </div>
              <p className="text-lg font-medium text-blue-700">Processing your request...</p>
            </div>
          </div>
        </div>
      )}

      {/* Centered Chat Panel */}
      <div className="w-full max-w-2xl mx-auto">
        <Card className="bg-gradient-to-br from-blue-50/80 to-indigo-50/80 backdrop-blur-md shadow-2xl border border-blue-200/50 rounded-3xl overflow-hidden">
          {/* Header with controls */}
          <div className="p-6 border-b border-blue-200/30 bg-gradient-to-r from-blue-100/50 to-indigo-100/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <Button
                  onClick={status === 'Connected' ? disconnect : connect}
                  className={`${
                    status === 'Connected' 
                      ? 'bg-gradient-to-r from-emerald-400 to-teal-500 hover:from-emerald-500 hover:to-teal-600' 
                      : 'bg-gradient-to-r from-blue-400 to-indigo-500 hover:from-blue-500 hover:to-indigo-600'
                  } text-white border-0 shadow-lg rounded-2xl w-14 h-14 flex items-center justify-center transition-all duration-200 hover:scale-105`}
                  size="icon"
                  aria-label={status === 'Connected' ? 'Disconnect' : 'Connect'}
                >
                  {status === 'Connected' ? <PowerOff size={22} /> : <Power size={22} />}
                </Button>
                <Button
                  onClick={recording ? stopRecording : startRecording}
                  disabled={status !== 'Connected'}
                  className={`${
                    recording 
                      ? 'bg-gradient-to-r from-red-400 to-pink-500 hover:from-red-500 hover:to-pink-600' 
                      : 'bg-gradient-to-r from-blue-400 to-indigo-500 hover:from-blue-500 hover:to-indigo-600'
                  } text-white border-0 shadow-lg rounded-2xl w-14 h-14 flex items-center justify-center transition-all duration-200 hover:scale-105 ${
                    status !== 'Connected' ? 'opacity-40 cursor-not-allowed' : ''
                  }`}
                  size="icon"
                  aria-label={recording ? 'Stop Recording' : 'Start Recording'}
                >
                  {recording ? <MicOff size={22} /> : <Mic size={22} />}
                </Button>
                <div className="flex-1">
                  {audioCaptureComponent}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`inline-block w-4 h-4 rounded-full ${
                  status === 'Connected' ? 'bg-emerald-400 shadow-emerald-200 shadow-lg animate-pulse' : 'bg-blue-300'
                } transition-all duration-200`} title={status}></span>
                <span className="text-sm font-medium text-blue-700">{status}</span>
              </div>
            </div>
          </div>

          {/* Chat messages */}
          <div ref={chatContainerRef} className="h-96 overflow-y-auto p-6 space-y-4">
            <AnimatePresence>
              {textOutputs.map((msg, i) => (
                <motion.div
                  key={i}
                  layout
                  initial="initial"
                  animate="animate"
                  exit="exit"
                  variants={messageVariants}
                  className={`flex items-start gap-3 ${
                    msg.role === 'USER' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  {msg.role === 'ASSISTANT' && (
                    <motion.div
                      variants={avatarVariants}
                      initial="initial"
                      animate="animate"
                    >
                      <Avatar className="bg-gradient-to-br from-blue-500 to-indigo-600 text-white w-10 h-10 ring-2 ring-offset-2 ring-blue-200/50 shadow-lg">
                        <AvatarImage src="/nova-sonic-avatar.png" alt="Assistant" />
                        <AvatarFallback><Bot size={18} /></AvatarFallback>
                      </Avatar>
                    </motion.div>
                  )}
                  <motion.div
                    className={`p-4 rounded-2xl shadow-sm max-w-[75%] text-sm font-medium backdrop-blur-sm border ${
                      msg.role === 'USER'
                        ? 'bg-gradient-to-r from-blue-500 to-indigo-600 text-white rounded-br-md shadow-lg border-blue-300/30'
                        : msg.role === 'SYSTEM'
                        ? 'bg-blue-100/80 text-blue-600 text-xs italic border-blue-200/50'
                        : msg.role === 'ASSISTANT'
                        ? 'bg-gradient-to-br from-blue-50/90 to-indigo-50/90 text-blue-800 rounded-bl-md shadow-md border-blue-200/50'
                        : 'bg-gradient-to-br from-blue-50/90 to-indigo-50/90 text-blue-800 border-blue-200/50'
                    }`}
                    whileHover={{ scale: 1.02 }}
                    transition={{ type: "spring", stiffness: 400, damping: 17 }}
                  >
                    {msg.text}
                  </motion.div>
                  {msg.role === 'USER' && (
                    <motion.div
                      variants={avatarVariants}
                      initial="initial"
                      animate="animate"
                    >
                      <Avatar className="bg-gradient-to-br from-blue-600 to-indigo-700 text-white w-10 h-10 ring-2 ring-offset-2 ring-blue-200/50 shadow-lg">
                        <AvatarFallback><User size={18} /></AvatarFallback>
                      </Avatar>
                    </motion.div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
            
            {/* Empty state */}
            {textOutputs.length === 0 && (
              <div className="flex items-center justify-center h-full">
                <div className="text-center bg-gradient-to-br from-blue-100/60 to-indigo-100/60 backdrop-blur-sm rounded-3xl p-12 border border-blue-200/40">
                  <div className="w-16 h-16 bg-gradient-to-br from-blue-200 to-indigo-200 rounded-2xl flex items-center justify-center mx-auto mb-6">
                    <Mic className="w-8 h-8 text-blue-600" />
                  </div>
                  <p className="text-lg font-semibold text-blue-800 mb-2">Start Conversation</p>
                  <p className="text-sm text-blue-600">Press the mic button to begin</p>
                </div>
              </div>
            )}
          </div>
        </Card>
      </div>
    </main>
  );
}