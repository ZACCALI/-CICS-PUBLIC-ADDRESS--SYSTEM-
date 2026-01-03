import React, { useState, useEffect, useRef } from 'react';
import { useApp } from '../../context/AppContext';
import { useAuth } from '../../context/AuthContext';
import api from '../../api/axios'; // Import API for direct Text Broadcast calls
import Modal from '../common/Modal';

const RealTime = () => {
  const { addSchedule, logActivity, updateLog, broadcastActive, broadcastPreparing, startBroadcast, stopBroadcast, broadcastStream, zones, setZones, emergencyActive, stopAllAudio, systemState } = useApp();
  const { currentUser, loading: authLoading } = useAuth();
  const [currentLogId, setCurrentLogId] = useState(null); // Track session log
  
  // Lock Logic
  const isSystemLoading = !systemState || authLoading;
  const activeTask = systemState?.active_task;

  // Lock if: Loading OR Active Task belongs to someone else
  const isLockedByOther = isSystemLoading || (activeTask && 
                          (activeTask.type === 'voice' || activeTask.type === 'text') && 
                          activeTask.data?.user !== (currentUser?.name || 'Admin'));

  const lockingUser = isSystemLoading ? 'System' : (isLockedByOther ? (activeTask?.data?.user || 'Another User') : null);
  
  // Ref for readable start time
  const startTimeStrRef = useRef('');
  const startTimeRef = useRef(null);
  
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const canvasRef = useRef(null);
  const animationFrameRef = useRef(null);
  const [textMessage, setTextMessage] = useState('');
  
  // Memoize Voices to avoid re-renders
  const voices = React.useMemo(() => [
      { name: 'AI Female (Human-like)', id: 'female' },
      { name: 'AI Male (Human-like)', id: 'male' }
  ], []);

  const [selectedVoice, setSelectedVoice] = useState('female');
  const mediaStreamRef = useRef(null);
  
  const [showModal, setShowModal] = useState(false);
  const [modalMessage, setModalMessage] = useState('');
  
  // Debounce Lock
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Remove old useEffect for voices

  const handleZoneChange = (zone) => {
    // STRICT LOCK: Prevent any zone changes if broadcasting, in emergency, or speaking
    if (broadcastActive || emergencyActive || isSpeaking) {
        setModalMessage("Cannot change zones while a broadcast or emergency is active.");
        setShowModal(true);
        return;
    }

    // Logic for Broadasting safety (Min 1 active)
    if (broadcastActive) {
        if (zone === 'All Zones') {
             // If unchecking All Zones, but we are broadcasting, check if it clears everything
             if (zones['All Zones']) {
                 setModalMessage('Cannot unselect all zones while broadcasting.');
                 setShowModal(true);
                 return;
             }
        } else {
             // If unchecking a specific zone, ensure it's not the LAST one
             if (zones[zone]) {
                 // Count active zones (excluding 'All Zones' key logic)
                 const activeCount = Object.keys(zones).filter(k => k !== 'All Zones' && zones[k]).length;
                 if (activeCount <= 1) {
                     setModalMessage('At least one zone must remain active during broadcast.');
                     setShowModal(true);
                     return;
                 }
             }
        }
    }

    if (zone === 'All Zones') {
        const newValue = !zones['All Zones'];
        const newZones = {};
        Object.keys(zones).forEach(k => newZones[k] = newValue);
        setZones(newZones);
    } else {
        // Toggle specific zone
        const newValue = !zones[zone];
        const newZones = { ...zones, [zone]: newValue };
        
        // Sync 'All Zones' checkbox
        // If unchecking any zone, 'All Zones' must be false.
        // If checking a zone, check if ALL others are now true -> set 'All Zones' to true.
        
        if (!newValue) {
            newZones['All Zones'] = false;
        } else {
            // Check if all OTHER real zones are true
            const allOthersTrue = Object.keys(newZones).filter(k => k !== 'All Zones' && k !== zone).every(k => newZones[k]);
            if (allOthersTrue) {
                newZones['All Zones'] = true;
            }
        }
        
        setZones(newZones);
    }
  };

  // Handle Visualizer locally when stream is active
  useEffect(() => {
    if (broadcastActive && broadcastStream) {
        // Setup Visualizer
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        const audioCtx = new AudioContext();
        audioContextRef.current = audioCtx;
        const analyser = audioCtx.createAnalyser();
        analyserRef.current = analyser;
        
        try {
            const source = audioCtx.createMediaStreamSource(broadcastStream);
            source.connect(analyser); // Connect for visualization
            analyser.fftSize = 256;
            drawVisualizer();
        } catch(e) { console.error(e); }

        const handleStop = () => {
            if (audioContextRef.current) audioContextRef.current.close();
            if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
        };
        window.addEventListener('stop-all-audio', handleStop);

        return () => {
            window.removeEventListener('stop-all-audio', handleStop);
            if (audioContextRef.current) audioContextRef.current.close();
            if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
        };
    }
  }, [broadcastActive, broadcastStream]);
  const drawVisualizer = () => {
      if (!analyserRef.current || !canvasRef.current) return;
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      const bufferLength = analyserRef.current.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      
      const draw = () => {
          animationFrameRef.current = requestAnimationFrame(draw);
          analyserRef.current.getByteFrequencyData(dataArray);
          
          ctx.clearRect(0, 0, canvas.width, canvas.height); // Clear instead of fill for transparent overlay
          
          const barWidth = (canvas.width / bufferLength) * 2.5;
          let barHeight;
          let x = 0;
          
          for (let i = 0; i < bufferLength; i++) {
              barHeight = dataArray[i] / 2;
              // Gradient Color
              ctx.fillStyle = `rgba(239, 68, 68, ${barHeight / 100})`; // Red based intensity
              ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);
              x += barWidth + 1;
          }
      };
      
      draw();
  };
  /* 
    TOGGLE BROADCAST LOGIC (Raw PCM Streaming)
    1. Start: Init AudioContext -> ScriptProcessor -> Start Broadcast (Lock) -> Record PCM -> Send
    2. Stop: Disconnect -> Stop Broadcast (Unlock)
  */
  // Audio Refs
  const processorRef = useRef(null);
  const sourceRef = useRef(null);
  const gainRef = useRef(null); // Gain Node for Muting
  // audioContextRef is already defined at top of component

  // Helper: Float32 to Int16 PCM
  const floatTo16BitPCM = (input) => {
      const output = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]));
          output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      return output;
  };

  const toggleBroadcast = async () => {
    if (isSubmitting) return; // Debounce
    
    if (emergencyActive) {
        setModalMessage("Emergency Alert is currently active. All broadcasts are suspended.");
        setShowModal(true);
        return;
    }

    // --- STOPPING ---
    if (broadcastActive) {
        // 1. Stop Audio Context logic
        if (processorRef.current) {
            processorRef.current.disconnect(); 
            processorRef.current.onaudioprocess = null;
            processorRef.current = null;
        }
        if (sourceRef.current) {
            sourceRef.current.disconnect(); 
            sourceRef.current = null;
        }
        if (gainRef.current) {
            gainRef.current.disconnect();
            gainRef.current = null;
        }
        if (audioContextRef.current) {
            audioContextRef.current.close(); 
            audioContextRef.current = null;
        }
        
        // 2. Stop Backend Session
        stopBroadcast(currentUser?.name || 'Admin');
        
        // 3. Log
        if (currentLogId) {
             const endTimeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
             updateLog(currentLogId, {
                 action: 'Voice Broadcast Session',
                 details: `Voice Broadcast (Start: ${startTimeStrRef.current} - End: ${endTimeStr})`
             });
             setCurrentLogId(null);
        }
        return;
    }

    // --- STARTING ---
    if (!Object.values(zones).some(z => z)) {
        setModalMessage('Please select at least one zone before broadcasting.');
        setShowModal(true);
        return;
    }
    
    // Safety Check for Microphone API (Requires HTTPS or Localhost)
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setModalMessage("Microphone Blocked! Browser requires HTTPS.\n\nTo fix on Chrome:\n1. Go to: chrome://flags/#unsafely-treat-insecure-origin-as-secure\n2. Enable it.\n3. Add: http://" + window.location.host + "\n4. Relaunch Chrome.");
        setShowModal(true);
        return;
    }

    setIsSubmitting(true);
    
    try {
        // 1. Start Backend Session (Locks system, Plays Intro on Pi)
        const success = await startBroadcast(currentUser?.name || 'Admin', zones);
        
        if (success) {
            startTimeRef.current = Date.now();
            startTimeStrRef.current = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            
            const logId = await logActivity(currentUser?.name, 'Active Voice Broadcast', 'Voice', 'Microphone is active...');
            setCurrentLogId(logId);
            
            // 2. Start Microphone & Audio Processing
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaStreamRef.current = stream;

            const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000, // Optimized for Pi (16kHz Voice)
            });
            audioContextRef.current = audioCtx;
            
            // Gain Node to MUTE local feedback
            const gainNode = audioCtx.createGain();
            gainNode.gain.value = 0; // Mute
            gainRef.current = gainNode;

            const source = audioCtx.createMediaStreamSource(stream);
            sourceRef.current = source;
            
            // ScriptProcessor (bufferSize, inputChannels, outputChannels)
            // 16384 samples @ 16kHz ~= 1s latency (Stable for Pi)
            const processor = audioCtx.createScriptProcessor(16384, 1, 1);
            processorRef.current = processor;

            processor.onaudioprocess = async (e) => {
                const inputData = e.inputBuffer.getChannelData(0);
                
                // Convert to Int16 PCM
                const pcm16 = floatTo16BitPCM(inputData);
                
                // Convert to Base64
                // Uint8Array view of the Int16Array
                const pcmBytes = new Uint8Array(pcm16.buffer);
                
                // Binary to Base64 String
                let binary = '';
                const len = pcmBytes.byteLength;
                for (let i = 0; i < len; i++) {
                    binary += String.fromCharCode(pcmBytes[i]);
                }
                const base64data = window.btoa(binary);

                // Send Chunk
                try {
                    await api.post('/realtime/speak', {
                        user: currentUser?.name || 'Admin',
                        audio_data: base64data
                    });
                } catch (err) {
                    console.error("Chunk send failed", err);
                }
            };
            
            // Connect Graph: Source -> Processor -> Gain -> Destination (Muted)
            source.connect(processor);
            processor.connect(gainNode);
            gainNode.connect(audioCtx.destination); // Keep graph alive but silent
        } 
    } catch (e) {
        console.error("Broadcast toggle error", e);
        setModalMessage(`Microphone Error: ${e.message}`);
        setShowModal(true);
    } finally {
        setIsSubmitting(false); 
    }
  };

  const handleTextBroadcast = async () => {
    if (isSubmitting) return; // Debounce
    
    if (emergencyActive) {
        setModalMessage("Emergency Alert is currently active. Text announcements are disabled.");
        setShowModal(true);
        return;
    }

    if (broadcastActive) {
        setModalMessage('Cannot send text announcement while voice broadcast is active.');
        setShowModal(true);
        return;
    }

    if (!textMessage.trim()) {
        setModalMessage('Please enter a message.');
        setShowModal(true);
        return;
    }

    if (!Object.values(zones).some(z => z)) {
        setModalMessage('Please select at least one zone.');
        setShowModal(true);
        return;
    }

    // Stop existing audio locally immediately for responsiveness
    stopAllAudio();
    
    // Lock Button
    setIsSubmitting(true);
    
    // --- SEND TEXT BROADCAST ---
    try {
        const zonesList = Object.keys(zones).filter(k => k !== 'All Zones' && zones[k]);
        
        // POST to /realtime/start (Text Type)
        // CRITICAL FIX: The endpoint '/realtime/text' DOES NOT EXIST. Use '/start'.
        await api.post('/realtime/start', {
            user: currentUser?.name || 'Admin',
            zones: zonesList, // Send list of strings, backend handles mapping if needed, or map here if backend expects ints?
                              // Looking at backend: "zones: List[str]". So strings are fine!
            type: 'text',
            content: textMessage,
            voice: selectedVoice
        });

        // Clear input on success
        setTextMessage('');
        
        // Log to Activity Log
        try {
             if (currentUser?.name) {
                await api.post('/logs', {
                    user: currentUser.name,
                    action: 'Broadcasted Text',
                    details: `Message: "${textMessage}"`, 
                    timestamp: new Date().toISOString()
                });
             }
        } catch (e) {
             console.warn("Log failed but broadcast sent", e);
        }

    } catch (err) {

        // Clear input on success
        setTextMessage('');
        
        // Log to Activity Log
        // Use 'api' here too for consistency
        try {
             if (currentUser?.name) {
                await api.post('/logs', {
                    user: currentUser.name,
                    action: 'Broadcasted Text',
                    details: `Message: "${textMessage}"`, 
                    timestamp: new Date().toISOString()
                });
             }
        } catch (e) {
             console.warn("Log failed but broadcast sent", e);
        }

    } catch (err) {
        console.error("Text Broadcast Failed", err);
        setModalMessage(
            err.response && err.response.status === 409 
            ? "System Busy: Another broadcast is active." 
            : "Failed to broadcast message."
        );
        setShowModal(true);
    } finally {
        setIsSubmitting(false); // Unlock
    }
  };

  // Determine if I am currently broadcasting text (Server-side)
  const isSpeaking = systemState?.active_task?.type === 'text' && 
                     systemState?.active_task?.data?.user === (currentUser?.name || 'Admin');

  return (
    <div className="space-y-6">
      {/* Header with Emergency Status */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <h2 className="text-2xl font-bold text-gray-800 flex items-center">
            <i className="material-icons mr-3 text-primary">campaign</i> Real-Time Announcement
          </h2>
          
          {emergencyActive && (
              <div className="flex items-center px-3 py-1 bg-red-100 text-red-700 rounded-full text-xs font-bold animate-pulse border border-red-200">
                  <i className="material-icons text-sm mr-1">warning</i> SUSPENDED FOR EMERGENCY
              </div>
          )}
      </div>

      {isLockedByOther && !emergencyActive && (
          <div className="bg-orange-100 border-l-4 border-orange-500 text-orange-800 p-4 rounded shadow-sm flex items-center animate-fade-in">
              <i className="material-icons text-2xl mr-3">lock</i>
              <div>
                  <p className="font-bold">System Busy</p>
                  <p className="text-sm">
                      <span className="font-semibold">{lockingUser}</span> is currently broadcasting. Please wait.
                  </p>
              </div>
          </div>
      )}

      {/* Live Broadcast */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-700 mb-4 flex items-center">
          <i className="material-icons mr-2 text-green-600">mic</i> Live Broadcast (Microphone)
        </h3>
        
        <div className="flex flex-col items-center justify-center p-6 md:p-12 bg-gray-50 rounded-lg border border-dashed border-gray-200 relative overflow-hidden min-h-[300px]">
           
           {/* Visualizer Canvas overlay */}
           {broadcastActive && (
               <canvas ref={canvasRef} width="600" height="200" className="absolute inset-x-0 bottom-0 w-full h-[150px] opacity-30 pointer-events-none" />
           )}

           <div className={`w-28 h-28 md:w-32 md:h-32 rounded-full flex items-center justify-center mb-6 transition-all duration-500 relative z-10 ${
               emergencyActive ? 'bg-gray-100' :
               broadcastActive ? 'bg-red-100 animate-pulse scale-110 shadow-lg' : 'bg-white shadow-sm'
           }`}>
             <i className={`material-icons text-5xl ${emergencyActive ? 'text-gray-300' : (broadcastActive ? 'text-red-500' : 'text-gray-400')}`}>
                 {emergencyActive ? 'block' : (broadcastActive ? 'sensors' : 'mic')}
             </i>
           </div>
           
           <button 
             onClick={toggleBroadcast}
             disabled={isLockedByOther || emergencyActive || isSubmitting || broadcastPreparing}
             className={`px-10 py-4 rounded-full font-bold shadow-xl transition-all transform active:scale-95 relative z-10 w-full max-w-[280px] ${
                 broadcastActive ? 'bg-red-600 hover:bg-red-700 text-white' : 
                 ((isLockedByOther || emergencyActive || isSubmitting || broadcastPreparing) ? 'bg-gray-300 text-gray-500 cursor-not-allowed shadow-none' : 'bg-primary hover:bg-primary-dark hover:scale-105 text-white')
             }`}
           >
             {isSystemLoading || isSubmitting || broadcastPreparing ? (broadcastPreparing ? 'PLAYING CHIME...' : 'PROCESSING...') : 
              (emergencyActive ? 'EMERGENCY ACTIVE' : (isLockedByOther ? 'SYSTEM BUSY' : (broadcastActive ? 'STOP BROADCAST' : 'START BROADCAST')))}
           </button>
           
           <div className="mt-6 text-center relative z-10">
                <p className={`text-sm font-bold tracking-tight transition-all duration-300 ${
                    emergencyActive ? 'text-red-600' :
                    broadcastActive ? 'text-red-700' : 'text-gray-400'
                }`}>
                    {emergencyActive ? "SYSTEM ACCESSED SUSPENDED" :
                     broadcastPreparing ? "Chime Playing..." :
                     broadcastActive ? "LIVE BROADCASTING..." : "Ready to Broadcast"}
                </p>
                <div className="mt-2 flex items-center justify-center text-[10px] text-gray-400 bg-white px-3 py-1 rounded-full border border-gray-100">
                    <i className="material-icons text-xs mr-1">volume_off</i>
                    LOCAL MONITORING MUTED
                </div>
           </div>
        </div>
      </div>

      {/* Text Broadcast */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-700 mb-4 flex items-center">
          <i className="material-icons mr-2 text-primary">text_fields</i> Text Announcement
        </h3>

        <textarea 
          value={textMessage}
          onChange={(e) => setTextMessage(e.target.value)}
          className="w-full p-4 border border-gray-200 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all resize-y min-h-[120px] mb-4"
          placeholder="Type your announcement here..."
        ></textarea>

        <div className="flex flex-col md:flex-row gap-4 justify-between items-center">
          <div className="w-full md:w-auto">
             <label className="text-sm font-medium text-gray-600 mr-3">Voice:</label>
             <select 
                value={selectedVoice}
                onChange={(e) => setSelectedVoice(e.target.value)}
                className="p-2 border border-gray-200 rounded-md bg-white text-gray-700 outline-none focus:border-primary max-w-full md:max-w-[200px]"
             >
               {voices.map(v => (
                   <option key={v.id} value={v.id}>{v.name}</option>
               ))}
             </select>
          </div>
          
          <button 
             onClick={handleTextBroadcast}
             disabled={isLockedByOther || broadcastActive || emergencyActive || isSubmitting || isSpeaking}
             className={`w-full md:w-auto px-6 py-2.5 rounded-lg shadow-md font-medium flex items-center justify-center transition-all ${isLockedByOther || broadcastActive || emergencyActive || isSubmitting || isSpeaking ? 'bg-gray-300 text-gray-500 cursor-not-allowed shadow-none' : 'bg-primary hover:bg-primary-dark text-white'}`}
           >
             <i className="material-icons mr-2">volume_up</i> {emergencyActive ? 'Emergency Active' : (isLockedByOther ? 'System Busy' : (broadcastActive ? 'Voice Active' : (isSubmitting ? 'Processing...' : (isSpeaking ? 'Speaking...' : 'Broadcast Text'))))}
           </button>
        </div>
      </div>

    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h3 className="text-lg font-semibold text-gray-700 mb-4">Select Zones:</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {Object.keys(zones).map((label, idx) => (
             <label key={idx} className="flex items-center space-x-3 p-3 border border-gray-100 rounded-lg hover:bg-gray-50 cursor-pointer transition-all duration-200 active:scale-95 shadow-sm hover:shadow-md">
               <input 
                 type="checkbox" 
                 checked={zones[label]}
                 onChange={() => handleZoneChange(label)}
                 className="w-5 h-5 text-primary rounded focus:ring-primary border-gray-300 transition-colors" 
               />
               <span className="text-gray-700 font-medium truncate text-sm sm:text-base">{label}</span>
             </label>
          ))}
        </div>
      </div>

      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Notice"
        footer={
           <button 
              onClick={() => setShowModal(false)}
              className="px-6 py-2 bg-primary text-white rounded-lg font-medium shadow-sm"
           >
              OK
           </button>
        }
      >
        <p className="text-gray-600">{modalMessage}</p>
      </Modal>
    </div>
  );
};

export default RealTime;
