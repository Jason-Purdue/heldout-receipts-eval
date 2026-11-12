"""The exact prompts and decoding settings used in Stages 2 and 3, and a client for llama-server's chat endpoint."""
import json, urllib.request

NONE = "None of these"
LETTERS = "ABCDE"
SEED = 20261105                   # option-order shuffle
BOOTSTRAP_ANCHOR_CHARS = 300      # cap on the source text shown per option
BOOTSTRAP_QUOTE_TOKENS = 60       # cap on a model's quote
SERVER_SEED = 431                 # greedy decoding makes the seed moot
SERVER_TIMEOUT_S = 300

INSTRUCTION = ("Below is a question about a document, and options taken from that document. Each option shows the "
               "exact text it came from. Choose the option that answers the question. If no option answers it, "
               f"choose \"{NONE}\".\n\n")

QUOTE_INSTRUCTION = ("Copy, word for word, the words from the source text that state the answer to the question. "
                     "If the source text does not state the answer, write NONE.\n\n")


def prompt(q, order):
    lines = [f"{LETTERS[i]}) {v}" + (f'   [source: "{a}"]' if a else "") for i, (v, a) in enumerate(order)]
    return INSTRUCTION + f"Question: {q}\n" + "\n".join(lines) + "\nAnswer:"


def verify_prompt(q, value, anchor):
    return (f"Question: {q}\nProposed answer: {value}\nSource text: \"{anchor}\"\n"
            f"Does the source text directly state that \"{value}\" is the answer to the question? Answer Yes or No.\nAnswer:")


def quote_prompt(q, value, anchor):
    return QUOTE_INSTRUCTION + f"Question: {q}\nProposed answer: {value}\nSource text: \"{anchor}\"\nWords that state the answer:"


class ServerBackend:
    """pick / verify / generate against llama-server's OpenAI-compatible chat endpoint (loopback)."""

    def __init__(self, url):
        self.url = url.rstrip("/")

    def chat(self, text, max_tokens, grammar=None, stop=None):
        body = {"messages": [{"role": "user", "content": text}], "max_tokens": max_tokens,
                "temperature": 0, "seed": SERVER_SEED, "stream": False}
        if grammar:
            body["grammar"] = grammar
        if stop:
            body["stop"] = stop
        req = urllib.request.Request(f"{self.url}/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=SERVER_TIMEOUT_S) as r:
            return json.load(r)["choices"][0]["message"]["content"]

    @staticmethod
    def one_of(options):
        return "root ::= " + " | ".join(f'"{o}"' for o in options)

    def pick(self, it, order):
        out = self.chat(prompt(it["q"], order), 1, grammar=self.one_of(LETTERS[:len(order)])).strip()
        return LETTERS.index(out)

    def verify(self, q, value, anchor):
        return self.chat(verify_prompt(q, value, anchor), 1, grammar=self.one_of(["Yes", "No"])).strip() == "Yes"

    def generate(self, text):
        out = self.chat(text, BOOTSTRAP_QUOTE_TOKENS, stop=["\n"])
        return out.strip().strip('"').strip()
