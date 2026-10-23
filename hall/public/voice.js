const ICE = {
  iceServers: [
    { urls: "stun:stun.cloudflare.com:3478" },
    { urls: "stun:stun.l.google.com:19302" },
  ],
};

const SCREEN = {
  video: {
    width: { ideal: 1920, max: 1920 },
    height: { ideal: 1080, max: 1080 },
    frameRate: { ideal: 60, max: 60 },
  },
  audio: false,
};

export function createVoiceSession({ getSocket, getMe, onState }) {
  let localStream = null;
  let screenStream = null;
  let muted = false;
  let sharing = false;
  let channelId = null;
  const peers = new Map(); // userId -> { pc, audio, video, meta, screenSender }
  let voiceUsers = [];

  function emit() {
    onState?.({
      active: Boolean(localStream && channelId),
      muted,
      sharing,
      channelId,
      peers: voiceUsers,
      localScreenStream: screenStream,
      remoteScreens: collectRemoteScreens(),
    });
  }

  function collectRemoteScreens() {
    const screens = {};
    for (const [userId, peer] of peers) {
      if (peer.video?.srcObject) screens[userId] = peer.video.srcObject;
    }
    return screens;
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
    peer.video?.remove();
    peers.delete(userId);
  }

  function clearPeers() {
    for (const userId of [...peers.keys()]) removePeer(userId);
  }

  async function renegotiate(peer) {
    if (!peer || peer.makingOffer) return;
    peer.makingOffer = true;
    try {
      const offer = await peer.pc.createOffer();
      await peer.pc.setLocalDescription(offer);
      send({
        type: "voice_signal",
        to: peer.meta.userId,
        signal: { kind: "offer", sdp: peer.pc.localDescription },
      });
    } finally {
      peer.makingOffer = false;
    }
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

    const video = document.createElement("video");
    video.autoplay = true;
    video.playsInline = true;
    video.muted = true;
    video.dataset.peerScreen = meta.userId;

    for (const track of stream.getAudioTracks()) {
      pc.addTrack(track, stream);
    }

    let screenSender = null;
    if (screenStream) {
      const [screenTrack] = screenStream.getVideoTracks();
      if (screenTrack) {
        screenSender = pc.addTrack(screenTrack, screenStream);
      }
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
      const track = event.track;
      const [remote] = event.streams;
      if (!remote) return;
      if (track.kind === "audio") {
        audio.srcObject = remote;
        return;
      }
      if (track.kind === "video") {
        video.srcObject = remote;
        track.addEventListener("ended", () => {
          if (video.srcObject === remote) video.srcObject = null;
          emit();
        });
        emit();
      }
    };

    pc.onconnectionstatechange = () => {
      if (["failed", "closed", "disconnected"].includes(pc.connectionState)) {
        // Keep entry; ICE may recover. Hard-remove on voice_leave.
      }
    };

    peers.set(meta.userId, { pc, audio, video, meta, polite, screenSender, makingOffer: false });
    return peers.get(meta.userId);
  }

  async function callPeer(meta) {
    const peer = await ensurePeer(meta, true);
    if (!peer) return;
    await renegotiate(peer);
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

  async function stopShare(silent = false) {
    if (!sharing && !screenStream) return;
    for (const peer of peers.values()) {
      if (peer.screenSender) {
        try {
          peer.pc.removeTrack(peer.screenSender);
        } catch {
          // ignore
        }
        peer.screenSender = null;
        if (!silent) renegotiate(peer).catch(() => {});
      }
    }
    if (screenStream) {
      for (const track of screenStream.getTracks()) track.stop();
      screenStream = null;
    }
    sharing = false;
    if (!silent) send({ type: "voice_share", sharing: false });
    emit();
  }

  async function startShare() {
    if (!channelId || !localStream) throw new Error("Join voice before sharing your screen");
    if (!navigator.mediaDevices?.getDisplayMedia) {
      throw new Error("This browser cannot share a screen");
    }
    if (sharing) return;
    const stream = await navigator.mediaDevices.getDisplayMedia(SCREEN);
    const [track] = stream.getVideoTracks();
    if (!track) {
      for (const item of stream.getTracks()) item.stop();
      throw new Error("No screen video track");
    }
    track.contentHint = "detail";
    try {
      await track.applyConstraints({
        width: { ideal: 1920, max: 1920 },
        height: { ideal: 1080, max: 1080 },
        frameRate: { ideal: 60, max: 60 },
      });
    } catch {
      // Browser may ignore some constraints after capture starts.
    }
    track.addEventListener("ended", () => {
      stopShare().catch(() => {});
    });
    screenStream = stream;
    sharing = true;
    send({ type: "voice_share", sharing: true });

    for (const peer of peers.values()) {
      peer.screenSender = peer.pc.addTrack(track, stream);
      renegotiate(peer).catch(() => {});
    }
    emit();
  }

  async function toggleShare() {
    if (sharing) await stopShare();
    else await startShare();
  }

  async function leave() {
    if (channelId) send({ type: "voice_leave" });
    await stopShare(true);
    clearPeers();
    if (localStream) {
      for (const track of localStream.getTracks()) track.stop();
      localStream = null;
    }
    channelId = null;
    voiceUsers = [];
    muted = false;
    sharing = false;
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
    for (const user of voiceUsers) {
      if (!user.sharing) {
        const peer = peers.get(user.userId);
        if (peer?.video) peer.video.srcObject = null;
      }
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
    startShare,
    stopShare,
    toggleShare,
    handleSocketMessage,
    getState: () => ({
      active: Boolean(localStream && channelId),
      muted,
      sharing,
      channelId,
      peers: voiceUsers,
      localScreenStream: screenStream,
      remoteScreens: collectRemoteScreens(),
    }),
  };
}
