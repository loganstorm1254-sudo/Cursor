"""Train Nova from scratch: a small word-level GPT (decoder-only transformer).

Reads corpus.txt, trains, then exports:
  - nova_model.bin   raw float32 weights (little-endian, fixed order)
  - nova_config.json model dims + vocabulary
  - testvector.json  prompt ids + reference logits for the Kotlin parity test
"""
import json
import math
import struct
import time

import torch
import torch.nn as nn
import torch.nn.functional as F

torch.manual_seed(1234)
torch.set_num_threads(4)

# --- hyperparameters ---
N_LAYER = 4
N_HEAD = 8
N_EMBD = 256
BLOCK = 128
BATCH = 32
MAX_STEPS = 6000
WARMUP = 100
LR = 3e-4
DEVICE = "cpu"

# --- data ---
text = open("corpus.txt").read()
words = text.split()
vocab = sorted(set(words))
stoi = {w: i for i, w in enumerate(vocab)}
V = len(vocab)
data = torch.tensor([stoi[w] for w in words], dtype=torch.long)
n_val = len(data) // 20
train_data, val_data = data[:-n_val], data[-n_val:]
print(f"tokens={len(data)} vocab={V}")


def get_batch(split):
    d = train_data if split == "train" else val_data
    ix = torch.randint(len(d) - BLOCK - 1, (BATCH,))
    x = torch.stack([d[i:i + BLOCK] for i in ix])
    y = torch.stack([d[i + 1:i + BLOCK + 1] for i in ix])
    return x, y


class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.ln1 = nn.LayerNorm(N_EMBD)
        self.qkv = nn.Linear(N_EMBD, 3 * N_EMBD)
        self.proj = nn.Linear(N_EMBD, N_EMBD)
        self.ln2 = nn.LayerNorm(N_EMBD)
        self.fc = nn.Linear(N_EMBD, 4 * N_EMBD)
        self.fc2 = nn.Linear(4 * N_EMBD, N_EMBD)

    def forward(self, x):
        B, T, C = x.shape
        h = self.ln1(x)
        q, k, v = self.qkv(h).split(N_EMBD, dim=2)
        hd = C // N_HEAD
        q = q.view(B, T, N_HEAD, hd).transpose(1, 2)
        k = k.view(B, T, N_HEAD, hd).transpose(1, 2)
        v = v.view(B, T, N_HEAD, hd).transpose(1, 2)
        att = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        att = att.transpose(1, 2).contiguous().view(B, T, C)
        x = x + self.proj(att)
        h = self.ln2(x)
        x = x + self.fc2(F.gelu(self.fc(h), approximate="tanh"))
        return x


class GPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.tok_emb = nn.Embedding(V, N_EMBD)
        self.pos_emb = nn.Embedding(BLOCK, N_EMBD)
        self.blocks = nn.ModuleList([Block() for _ in range(N_LAYER)])
        self.lnf = nn.LayerNorm(N_EMBD)
        self.apply(self._init)

    def _init(self, m):
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, std=0.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.zeros_(m.bias)

    def forward(self, idx, targets=None):
        B, T = idx.shape
        x = self.tok_emb(idx) + self.pos_emb(torch.arange(T, device=idx.device))
        for b in self.blocks:
            x = b(x)
        x = self.lnf(x)
        logits = x @ self.tok_emb.weight.T  # tied weights
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.view(-1, V), targets.view(-1))
        return logits, loss


model = GPT()
n_params = sum(p.numel() for p in model.parameters())
print(f"params={n_params/1e6:.2f}M")
opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)


def lr_at(step):
    if step < WARMUP:
        return LR * (step + 1) / WARMUP
    t = (step - WARMUP) / (MAX_STEPS - WARMUP)
    return 0.1 * LR + 0.9 * LR * 0.5 * (1 + math.cos(math.pi * t))


@torch.no_grad()
def eval_loss():
    model.eval()
    losses = []
    for _ in range(20):
        x, y = get_batch("val")
        _, l = model(x, y)
        losses.append(l.item())
    model.train()
    return sum(losses) / len(losses)


t0 = time.time()
for step in range(MAX_STEPS):
    for g in opt.param_groups:
        g["lr"] = lr_at(step)
    x, y = get_batch("train")
    _, loss = model(x, y)
    opt.zero_grad(set_to_none=True)
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    opt.step()
    if step % 100 == 0 or step == MAX_STEPS - 1:
        vl = eval_loss()
        el = time.time() - t0
        print(f"step {step:5d} train {loss.item():.4f} val {vl:.4f} "
              f"lr {lr_at(step):.2e} elapsed {el/60:.1f}m", flush=True)
        torch.save(model.state_dict(), "ckpt.pt")

torch.save(model.state_dict(), "ckpt.pt")
print("training done")

# --- sample generations ---
model.eval()


@torch.no_grad()
def generate(prompt_words, max_new=80, temp=0.8, topk=40):
    ids = [stoi.get(w, stoi["<unk>"]) for w in prompt_words]
    for _ in range(max_new):
        ctx = torch.tensor([ids[-BLOCK:]], dtype=torch.long)
        logits, _ = model(ctx)
        logits = logits[0, -1] / temp
        v, _ = torch.topk(logits, topk)
        logits[logits < v[-1]] = -float("inf")
        probs = F.softmax(logits, dim=-1)
        nxt = torch.multinomial(probs, 1).item()
        ids.append(nxt)
        if vocab[nxt] == "<end>":
            break
    return " ".join(vocab[i] for i in ids)


for p in ["<user> hello <bot>", "<user> tell me a joke <bot>",
          "<user> who are you <bot>", "<user> what is 3 plus 4 <bot>",
          "<user> what is the capital of france <bot>",
          "<user> tell me a fact <bot>", "<user> i am sad <bot>",
          "<user> name 3 colors <bot>", "<user> what are the seasons <bot>",
          "<user> what is the opposite of hot <bot>",
          "<user> name some animals <bot>"]:
    print("SAMPLE:", generate(p.split()))

# --- export weights ---
sd = model.state_dict()
order = ["tok_emb.weight", "pos_emb.weight"]
for i in range(N_LAYER):
    for name in ["ln1.weight", "ln1.bias", "qkv.weight", "qkv.bias",
                 "proj.weight", "proj.bias", "ln2.weight", "ln2.bias",
                 "fc.weight", "fc.bias", "fc2.weight", "fc2.bias"]:
        order.append(f"blocks.{i}.{name}")
order += ["lnf.weight", "lnf.bias"]

with open("nova_model.bin", "wb") as f:
    for name in order:
        t = sd[name].float().contiguous().view(-1)
        f.write(struct.pack(f"<{t.numel()}f", *t.tolist()))

config = {"n_layer": N_LAYER, "n_head": N_HEAD, "n_embd": N_EMBD,
          "block_size": BLOCK, "vocab": vocab}
with open("nova_config.json", "w") as f:
    json.dump(config, f)

# --- test vector for Kotlin parity test ---
tv_prompt = "<user> tell me a joke <bot>".split()
tv_ids = [stoi[w] for w in tv_prompt]
with torch.no_grad():
    logits, _ = model(torch.tensor([tv_ids]))
last = logits[0, -1]
tv = {"prompt_ids": tv_ids,
      "logits_first16": [round(float(x), 4) for x in last[:16]],
      "argmax": int(last.argmax()),
      "argmax_word": vocab[int(last.argmax())]}
with open("testvector.json", "w") as f:
    json.dump(tv, f, indent=1)
print("export done:", tv["argmax_word"])
