"""Quick greedy-decoding accuracy check on math and capitals."""
import json
import torch
import torch.nn as nn
import torch.nn.functional as F

cfg = json.load(open("nova_config.json"))
N_LAYER, N_HEAD, N_EMBD, BLOCK = cfg["n_layer"], cfg["n_head"], cfg["n_embd"], cfg["block_size"]
vocab = cfg["vocab"]
V = len(vocab)
stoi = {w: i for i, w in enumerate(vocab)}


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

    def forward(self, idx):
        B, T = idx.shape
        x = self.tok_emb(idx) + self.pos_emb(torch.arange(T))
        for b in self.blocks:
            x = b(x)
        return self.lnf(x) @ self.tok_emb.weight.T


m = GPT()
m.load_state_dict(torch.load("ckpt.pt"))
m.eval()

WORDNUM = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
           7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve",
           13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen",
           18: "eighteen", 19: "nineteen", 20: "twenty"}


@torch.no_grad()
def greedy(prompt, max_new=40):
    ids = [stoi.get(w, stoi["<unk>"]) for w in prompt.split()]
    for _ in range(max_new):
        logits = m(torch.tensor([ids[-BLOCK:]]))
        nxt = int(logits[0, -1].argmax())
        ids.append(nxt)
        if vocab[nxt] == "<end>":
            break
    return " ".join(vocab[i] for i in ids)


ok = tot = 0
wrong = []
for a in range(0, 16):
    for b in range(0, 16):
        out = greedy(f"<user> what is {a} plus {b} <bot>")
        ans = out.split("<bot>")[1]
        r = a + b
        good = (WORDNUM.get(r, str(r)) in ans.split())
        ok += good
        tot += 1
        if not good:
            wrong.append(f"{a}+{b} -> {ans.strip()}")
for w in wrong[:8]:
    print("WRONG:", w)
print(f"addition accuracy: {ok}/{tot} = {ok/tot:.0%}")

caps = {"france": "paris", "japan": "tokyo", "italy": "rome", "spain": "madrid",
        "germany": "berlin", "england": "london", "russia": "moscow",
        "china": "beijing", "egypt": "cairo", "india": "delhi",
        "brazil": "brasilia", "canada": "ottawa", "australia": "canberra"}
ok = 0
for c, cap in caps.items():
    out = greedy(f"<user> what is the capital of {c} <bot>")
    good = cap in out.split("<bot>")[1]
    ok += good
    if not good:
        print("WRONG CAP:", c, "->", out.split("<bot>")[1].strip())
print(f"capitals accuracy: {ok}/{len(caps)}")
