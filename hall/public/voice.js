const ICE = {
  iceServers: [
    { urls: "stun:stun.cloudflare.com:3478" },
    { urls: "stun:stun.l.google.com:19302" },
  ],
};

const SCREEN_VIDEO = {
  width: { ideal: 1920, max: 1920 },
  height: { ideal: 1080, max: 1080 },
  frameRate: { ideal: 60, max: 60 },
};

/** System / tab audio — Chrome shows “Share audio” in the picker. */
const SCREEN_AUDIO = {
  echoCancellation: false,
  noiseSuppression: false,
  autoGainControl: false,
};

export function createVoiceSession({ getSocket, getMe, onState }) {
  let localStream = null;
  let screenStream = null;
  let muted = false;
  let sharing = false;
  let channelId = null;
  const peers = new Map(); // userId -> peer
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

  function assertMicLive() {
    if (!localStream) return;
    for (const track of localStream.getAudioTracks()) {
      track.enabled = !muted;
    }
    const [mic] = localStream.getAudioTracks();
    if (!mic) return;
    for (const peer of peers.values()) {
      // Never touch the screen-audio sender — only keep the mic sender alive.
      const audioSender = peer.audioSender;
      if (!audioSender || audioSender === peer.screenAudioSender) continue;
      if (audioSender.track !== mic) {
        audioSender.replaceTrack(mic).catch(() => {});
      }
    }
  }

  async function captureScreen() {
    try {
      return await navigator.mediaDevices.getDisplayMedia({
        video: SCREEN_VIDEO,
        audio: SCREEN_AUDIO,
      });
    } catch (error) {
      // Some surfaces reject audio; still share video.
      if (error?.name === "NotAllowedError") throw error;
      return navigator.mediaDevices.getDisplayMedia({
        video: SCREEN_VIDEO,
        audio: false,
      });
    }
  }

  function bindScreenAudio(peer, stream) {
    const [screenAudio] = stream.getAudioTracks();
    if (!screenAudio) return;
    screenAudio.contentHint = "music";
    if (peer.screenAudioSender) {
      peer.screenAudioSender.replaceTrack(screenAudio).catch(() => {});
      return;
    }
    peer.screenAudioSender = peer.pc.addTrack(screenAudio, stream);
  }

  function clearScreenAudio(peer) {
    if (!peer.screenAudioSender) return;
    try {
      peer.pc.removeTrack(peer.screenAudioSender);
    } catch {
      // ignore
    }
    peer.screenAudioSender = null;
  }

  async function ensureMic() {
    if (localStream) {
      assertMicLive();
      return localStream;
    }
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
    if (!peer) return;
    // Queue so share + glare fixes do not overlap on one PC.
    peer.chain = (peer.chain || Promise.resolve()).then(async () => {
      if (peer.makingOffer || peer.pc.signalingState !== "stable") return;
      peer.makingOffer = true;
      try {
        assertMicLive();
        const offer = await peer.pc.createOffer();
        if (peer.pc.signalingState !== "stable") return;
        await peer.pc.setLocalDescription(offer);
        send({
          type: "voice_signal",
          to: peer.meta.userId,
          signal: { kind: "offer", sdp: peer.pc.localDescription },
        });
      } finally {
        peer.makingOffer = false;
      }
    }).catch(() => {});
    return peer.chain;
  }

  async function ensurePeer(meta) {
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

    // Mic first so m-line order stays stable across renegotiation.
    let audioSender = null;
    for (const track of stream.getAudioTracks()) {
      audioSender = pc.addTrack(track, stream);
    }

    // Pre-create a video transceiver so screen share is replaceTrack, not a new m-line fight.
    const videoTransceiver = pc.addTransceiver("video", { direction: "recvonly" });
    let screenAudioSender = null;
    if (screenStream) {
      const [screenTrack] = screenStream.getVideoTracks();
      if (screenTrack) {
        await videoTransceiver.sender.replaceTrack(screenTrack);
        videoTransceiver.direction = "sendrecv";
      }
      for (const screenAudio of screenStream.getAudioTracks()) {
        screenAudio.contentHint = "music";
        screenAudioSender = pc.addTrack(screenAudio, screenStream);
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
      if (track.kind === "audio") {
        // Mic + screen audio can both arrive — play them together.
        let dest = audio.srcObject;
        if (!(dest instanceof MediaStream)) {
          dest = new MediaStream();
          audio.srcObject = dest;
        }
        if (!dest.getAudioTracks().includes(track)) dest.addTrack(track);
        track.addEventListener("ended", () => {
          try {
            dest.removeTrack(track);
          } catch {
            // ignore
          }
        });
        track.addEventListener("unmute", () => {
          void audio.play().catch(() => {});
        });
        void audio.play().catch(() => {});
        return;
      }
      if (track.kind === "video") {
        video.srcObject = new MediaStream([track]);
        void video.play().catch(() => {});
        track.addEventListener("ended", () => {
          if (video.srcObject) video.srcObject = null;
          emit();
        });
        emit();
      }
    };

    const peer = {
      pc,
      audio,
      video,
      meta,
      audioSender,
      screenAudioSender,
      videoTransceiver,
      makingOffer: false,
      ignoreOffer: false,
      chain: Promise.resolve(),
    };
    peers.set(meta.userId, peer);
    return peer;
  }

  async function callPeer(meta) {
    const peer = await ensurePeer(meta);
    if (!peer) return;
    await renegotiate(peer);
  }

  async function handleSignal(from, signal, meta) {
    const me = getMe?.();
    if (!me || from === me.id || !signal) return;
    const peer = await ensurePeer(meta || { userId: from, displayName: from, username: from });
    if (!peer) return;

    peer.chain = (peer.chain || Promise.resolve()).then(async () => {
      if (signal.kind === "offer") {
        // Perfect negotiation: higher id is polite.
        const polite = me.id > from;
        const collision = peer.makingOffer || peer.pc.signalingState !== "stable";
        peer.ignoreOffer = !polite && collision;
        if (peer.ignoreOffer) return;
        if (collision) {
          try {
            await Promise.all([
              peer.pc.setLocalDescription({ type: "rollback" }),
              peer.pc.setRemoteDescription(signal.sdp),
            ]);
          } catch {
            await peer.pc.setRemoteDescription(signal.sdp);
          }
        } else {
          await peer.pc.setRemoteDescription(signal.sdp);
        }
        assertMicLive();
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
        if (peer.ignoreOffer) return;
        if (peer.pc.signalingState === "have-local-offer") {
          await peer.pc.setRemoteDescription(signal.sdp);
          assertMicLive();
        }
        return;
      }
      if (signal.kind === "ice" && signal.candidate) {
        try {
          await peer.pc.addIceCandidate(signal.candidate);
        } catch {
          if (!peer.ignoreOffer) {
            // Out-of-order ICE is common during setup.
          }
        }
      }
    }).catch(() => {});
    return peer.chain;
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
      try {
        await peer.videoTransceiver?.sender.replaceTrack(null);
        if (peer.videoTransceiver) peer.videoTransceiver.direction = "recvonly";
      } catch {
        // ignore
      }
      clearScreenAudio(peer);
      if (!silent) renegotiate(peer).catch(() => {});
    }
    if (screenStream) {
      for (const track of screenStream.getTracks()) track.stop();
      screenStream = null;
    }
    sharing = false;
    if (!silent) send({ type: "voice_share", sharing: false });
    assertMicLive();
    emit();
  }

  async function startShare() {
    if (!channelId || !localStream) throw new Error("Join voice before sharing your screen");
    if (!navigator.mediaDevices?.getDisplayMedia) {
      throw new Error("This browser cannot share a screen");
    }
    if (sharing) return;
    const stream = await captureScreen();
    const [track] = stream.getVideoTracks();
    if (!track) {
      for (const item of stream.getTracks()) item.stop();
      throw new Error("No screen video track");
    }
    track.contentHint = "detail";
    try {
      await track.applyConstraints(SCREEN_VIDEO);
    } catch {
      // Browser may ignore some constraints after capture starts.
    }
    track.addEventListener("ended", () => {
      stopShare().catch(() => {});
    });
    for (const screenAudio of stream.getAudioTracks()) {
      screenAudio.addEventListener("ended", () => {
        for (const peer of peers.values()) clearScreenAudio(peer);
      });
    }
    screenStream = stream;
    sharing = true;
    // Display capture on Windows can soft-drop mic senders — put mic back before video.
    assertMicLive();
    send({ type: "voice_share", sharing: true });

    for (const peer of peers.values()) {
      try {
        if (!peer.videoTransceiver) {
          peer.videoTransceiver = peer.pc.addTransceiver("video", { direction: "sendrecv" });
        }
        await peer.videoTransceiver.sender.replaceTrack(track);
        peer.videoTransceiver.direction = "sendrecv";
      } catch {
        peer.pc.addTrack(track, stream);
      }
      bindScreenAudio(peer, stream);
      await renegotiate(peer);
    }
    assertMicLive();
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
    assertMicLive();
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
