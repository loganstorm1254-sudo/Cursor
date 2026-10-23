const ICE = {
  iceServers: [
    { urls: "stun:stun.cloudflare.com:3478" },
    { urls: "stun:stun.l.google.com:19302" },
  ],
};

export function createVoiceSession({ getSocket, getMe, onState }) {
  let localStream = null;
  let muted = false;
  let channelId = null;
  const peers = new Map(); // userId -> { pc, audio, meta }
  let voiceUsers = [];

  function emit() {
    onState?.({
      active: Boolean(localStream && channelId),
      muted,
      channelId,
      peers: voiceUsers,
    });
  }

  function send(payload) {
    const socket = getSocket?.();
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify(payload));
  }

  async function ensureMic() {
    if (localStream) return localStream;
    localStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });
    for (const track of localStream.getAudioTracks()) track.enabled = !muted;
    return localStream;
  }

  function removePeer(userId) {
    const peer = peers.get(userId);
    if (!peer) return;
    try {
      peer.pc.close();
    } catch {
      // ignore
    }
    peer.audio?.remove();
    peers.delete(userId);
  }

  function clearPeers() {
    for (const userId of [...peers.keys()]) removePeer(userId);
  }

  async function ensurePeer(meta, polite) {
    const me = getMe?.();
    if (!me || meta.userId === me.id || peers.has(meta.userId)) return peers.get(meta.userId);
    const stream = await ensureMic();
    const pc = new RTCPeerConnection(ICE);
    const audio = document.createElement("audio");
    audio.autoplay = true;
    audio.playsInline = true;
    audio.dataset.peer = meta.userId;
    document.body.append(audio);

    for (const track of stream.getAudioTracks()) {
      pc.addTrack(track, stream);
    }

    pc.onicecandidate = (event) => {
      if (!event.candidate) return;
      send({
        type: "voice_signal",
        to: meta.userId,
        signal: { kind: "ice", candidate: event.candidate.toJSON() },
      });
    };

    pc.ontrack = (event) => {
      const [remote] = event.streams;
      if (remote) audio.srcObject = remote;
    };

    pc.onconnectionstatechange = () => {
      if (["failed", "closed", "disconnected"].includes(pc.connectionState)) {
        // Keep entry; ICE may recover. Hard-remove on voice_leave.
      }
    };

    peers.set(meta.userId, { pc, audio, meta, polite });
    return peers.get(meta.userId);
  }

  async function callPeer(meta) {
    const peer = await ensurePeer(meta, true);
    if (!peer || peer.makingOffer) return;
    peer.makingOffer = true;
    try {
      const offer = await peer.pc.createOffer();
      await peer.pc.setLocalDescription(offer);
      send({
        type: "voice_signal",
        to: meta.userId,
        signal: { kind: "offer", sdp: peer.pc.localDescription },
      });
    } finally {
      peer.makingOffer = false;
    }
  }

  async function handleSignal(from, signal, meta) {
    const me = getMe?.();
    if (!me || from === me.id || !signal) return;
    const peer = await ensurePeer(meta || { userId: from, displayName: from, username: from }, false);
    if (!peer) return;

    if (signal.kind === "offer") {
      await peer.pc.setRemoteDescription(signal.sdp);
      const answer = await peer.pc.createAnswer();
      await peer.pc.setLocalDescription(answer);
      send({
        type: "voice_signal",
        to: from,
        signal: { kind: "answer", sdp: peer.pc.localDescription },
      });
      return;
    }
    if (signal.kind === "answer") {
      if (peer.pc.signalingState === "have-local-offer") {
        await peer.pc.setRemoteDescription(signal.sdp);
      }
      return;
    }
    if (signal.kind === "ice" && signal.candidate) {
      try {
        await peer.pc.addIceCandidate(signal.candidate);
      } catch {
        // Out-of-order ICE is common during setup.
      }
    }
  }

  async function join(nextChannelId) {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("This browser cannot use voice chat");
    }
    if (channelId && channelId !== nextChannelId) await leave();
    channelId = nextChannelId;
    await ensureMic();
    send({ type: "voice_join" });
    emit();
  }

  async function leave() {
    if (channelId) send({ type: "voice_leave" });
    clearPeers();
    if (localStream) {
      for (const track of localStream.getTracks()) track.stop();
      localStream = null;
    }
    channelId = null;
    voiceUsers = [];
    muted = false;
    emit();
  }

  function setMuted(next) {
    muted = Boolean(next);
    if (localStream) {
      for (const track of localStream.getAudioTracks()) track.enabled = !muted;
    }
    send({ type: "voice_mute", muted });
    emit();
  }

  function toggleMute() {
    setMuted(!muted);
  }

  function onVoiceState(list) {
    voiceUsers = Array.isArray(list) ? list : [];
    const me = getMe?.();
    const ids = new Set(voiceUsers.map((user) => user.userId));
    for (const userId of [...peers.keys()]) {
      if (!ids.has(userId)) removePeer(userId);
    }
    emit();
    if (!localStream || !me) return;
    for (const user of voiceUsers) {
      if (user.userId === me.id) continue;
      if (!peers.has(user.userId) && me.id < user.userId) {
        // Lower id initiates — avoids glare.
        callPeer(user).catch(() => {});
      }
    }
  }

  function handleSocketMessage(payload) {
    if (payload.type === "voice_state") {
      onVoiceState(payload.voice ?? []);
      return true;
    }
    if (payload.type === "voice_signal" && payload.from && payload.signal) {
      handleSignal(payload.from, payload.signal, payload.fromUser).catch(() => {});
      return true;
    }
    return false;
  }

  return {
    join,
    leave,
    toggleMute,
    setMuted,
    handleSocketMessage,
    getState: () => ({
      active: Boolean(localStream && channelId),
      muted,
      channelId,
      peers: voiceUsers,
    }),
  };
}
