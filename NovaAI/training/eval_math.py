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


def check(problems, label):
    ok = tot = 0
    wrong = []
    for q, r in problems:
        out = greedy(f"<user> {q} <bot>")
        ans = out.split("<bot>")[1]
        good = (WORDNUM.get(r, str(r)) in ans.split()
                if isinstance(r, int) else str(r) in ans)
        ok += good
        tot += 1
        if not good:
            wrong.append(f"{q} -> {ans.strip()}")
    for w in wrong[:6]:
        print(f"WRONG {label}:", w)
    print(f"{label} accuracy: {ok}/{tot} = {ok/tot:.0%}")


check([(f"what is {a} plus {b}", a + b)
       for a in range(0, 21) for b in range(0, 21, 2)], "addition")
check([(f"what is {a} minus {b}", a - b)
       for a in range(0, 26, 2) for b in range(0, a + 1, 3)], "subtraction")
check([(f"what is {a} times {b}", a * b)
       for a in range(1, 13) for b in range(1, 13)], "multiplication")
check([(f"what is {b * q} divided by {b}", q)
       for b in range(1, 13) for q in range(0, 13, 2)], "division")

caps = {"france": "paris", "japan": "tokyo", "italy": "rome", "spain": "madrid",
        "germany": "berlin", "england": "london", "russia": "moscow",
        "china": "beijing", "egypt": "cairo", "india": "delhi",
        "brazil": "brasilia", "canada": "ottawa", "australia": "canberra",
        "greece": "athens", "poland": "warsaw", "sweden": "stockholm",
        "turkey": "ankara", "south korea": "seoul", "thailand": "bangkok",
        "argentina": "buenos aires", "kenya": "nairobi", "ukraine": "kyiv",
        "norway": "oslo", "portugal": "lisbon", "iceland": "reykjavik"}
check([(f"what is the capital of {c}", cap) for c, cap in caps.items()],
      "capitals")

spell = ["cat", "friend", "school", "because", "february", "elephant",
         "butterfly", "chocolate", "beautiful", "wednesday"]
check([(f"how do you spell {w}", " ".join(w)) for w in spell], "spelling")

states = {"texas": "austin", "california": "sacramento", "florida": "tallahassee",
          "new york": "albany", "ohio": "columbus", "georgia": "atlanta",
          "washington state": "olympia", "arizona": "phoenix",
          "colorado": "denver", "michigan": "lansing", "nevada": "carson city",
          "hawaii": "honolulu"}
check([(f"what is the capital of {s}", cap) for s, cap in states.items()],
      "state capitals")

elements = {"gold": "au", "oxygen": "o", "iron": "fe", "hydrogen": "h",
            "sodium": "na", "silver": "ag", "carbon": "c", "helium": "he",
            "copper": "cu", "lead": "pb"}
check([(f"what is the chemical symbol for {e}", s)
       for e, s in elements.items()], "element symbols")
