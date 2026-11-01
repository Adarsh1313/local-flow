"""Starter words: built-in names and terms the speech model often mishears, in groups
you can switch off one by one. Kept apart from your own Dictionary, which wins when
both know a word. Pure data plus the swap: no UI.

Each line reads "Written = heard | heard": every heard form is swapped for the written
one. A line with no "=" is a word the model should know but that has no common
mishearing yet (it still goes to the speech model as a hint where the engine takes one).
Heard forms are chosen so they don't occur in normal sentences: "cloud code", never
"cloud" on its own."""
from dictionary import swap

GROUPS = {
    "tech": ("Tech and AI", """
ChatGPT = chatgpt | chat gpt | chat g p t | chad gpt | chat GBT | chatgbt | chat jpt | cha gpt
GPT-4o = gpt four o | gpt 4 o | gpt foro
GPT-5 = gpt five | gpt 5
OpenAI = open ai | open a i | open eye
Claude = claud | clawed ai | cloud ai
Claude Code = cloud code | clawed code | claud code | clod code
Anthropic = anthropik | and tropic | anthro pic
Codex = codecs cli | code x
Gemini = gemini ai | jemini
Google AI Studio = google a i studio
Antigravity = anti gravity | anti-gravity
Copilot = co-pilot | co pilot
GitHub Copilot = github co-pilot | git hub copilot
Cursor = cursor ai | curser ai
Windsurf = wind surf
Perplexity = perplexity ai
Midjourney = mid journey
Hugging Face = hugging phase | huggingface
LLaMA = llama model
Ollama = o llama | oh llama | olama
Mistral = mistral ai
DeepSeek = deep seek | deepseek
Grok = grok ai
xAI = x ai | x a i
Parakeet
Whisper = whisper ai
LangChain = lang chain | langchain
LlamaIndex = llama index
RAG = rag pipeline | r a g
LLM = l l m | llms | l l ms
LLMs = l l m s
API = a p i
APIs = a p is | a p i s
SDK = s d k
CLI = c l i
MCP = m c p
MCP server = m c p server | mcp server
JSON = jason file | j son
YAML = yaml file | yamel
SQL = s q l | sequel query
NoSQL = no sql | no sequel
PostgreSQL = postgres sql | post gres | postgre sql
Postgres = post gress
MongoDB = mongo db | mongo d b
Redis = reddis | redis cache
Supabase = supa base | super base | supabase
Firebase = fire base
Vercel = versel | ver cell | vercel
Netlify = net lify | netlify
Cloudflare = cloud flare
AWS = a w s
GCP = g c p
Azure = azure cloud
Kubernetes = kubernetes | cuber netes | kubernetties
Docker = docker file
Dockerfile = docker file
GitHub = github | git hub
GitLab = gitlab | git lab
Git = git repo
npm = n p m
pnpm = p n p m
Node.js = node js | node j s | nodejs
Next.js = next js | next j s | nextjs
React = react js
React Native = react native
TypeScript = typescript | type script
JavaScript = javascript | java script
Python
PyTorch = pie torch | py torch | pytorch
TensorFlow = tensor flow
NumPy = num py | numpy | number pie
pandas = panda's dataframe
Jupyter = jupiter notebook | jupyter
Tailwind = tail wind | tailwind css
Vite = veet | vite js
Svelte = svelt
FastAPI = fast api | fast a p i
Django = jango
Flask = flask app
VS Code = vs code | v s code | visual studio code
JetBrains = jet brains | jed brains
IntelliJ = intellij | intelli j
Xcode = x code
Figma = figma file | fig ma
Framer = framer motion
Vibe coding = vibe coding | vibe-coding
vibe-coded = vibe coded | wipe coded
vibe code = wipe code
UI = u i
UX = u x
UI/UX = u i u x | ui ux
CSS = c s s
HTML = h t m l
URL = u r l
OAuth = o auth | oh auth
JWT = j w t
CI/CD = c i c d | ci cd
PR = p r
PRs = p rs | p r s
repo = ripo
localhost = local host
LocalFlow = local flow
Wispr Flow = whisper flow | wisper flow
AgentKanban = agent kanban | agent con ban
Spotify
tokens
prompt engineering
fine-tuning = fine tuning
fine-tune = fine tune
GPU = g p u
CPU = c p u
NVIDIA = nvidia | n video | in video
RTX = r t x
Hugging Face Hub = hugging face hub
Colab = co lab | collab notebook
Kaggle = kaggel
"""),
    "apps": ("Apps and brands", """
WhatsApp = whatsapp | whats app | what's app
YouTube = youtube | you tube
LinkedIn = linkedin | linked in
Instagram = insta gram
Facebook = face book
TikTok = tik tok | tick tock app
Snapchat = snap chat
Reddit = read it app | reddit
Discord = discord server
Telegram = telegram app
Gmail = g mail | gee mail
Google Docs = google docs
Google Sheets = google sheets
Google Drive = google drive
Google Meet = google meet
Notion = notion page | notion doc | notion app
Slack = slack channel | slack message
Zoom = zoom call | zoom meeting
Microsoft Teams = ms teams | m s teams
Outlook = outlook mail
OneDrive = one drive
PowerPoint = power point
Excel = excel sheet
Canva = canva design | canvas design
Trello = trello board
Jira = jira ticket | jeera
Asana = asana task
Airtable = air table
Zapier = zapier | zappier
Calendly = calendly | calendar lee
Loom = loom video
Miro = miro board
Stripe = stripe payment
PayPal = pay pal
Razorpay = razor pay
Paytm = pay tm | paytm
PhonePe = phone pay | phone pe
Google Pay = google pay | g pay
UPI = u p i
Zomato = zomato | zomatto
Swiggy = swiggy | swiggi
Zepto = zepto | zeptoh
Blinkit = blink it
BigBasket = big basket
Flipkart = flip kart | flip cart
Amazon = amazon prime
Myntra = myntra | mintra
Nykaa = nykaa | nyka | naika
Meesho = meesho | mesho
Ola = ola cab
Uber = uber ride
Rapido = rapido bike
MakeMyTrip = make my trip
IRCTC = i r c t c
Netflix = net flix
Hotstar = hot star
JioCinema = jio cinema
Jio = geo sim | jio sim
Airtel = air tel
Spotify = spot ify | spotify
Apple Music = apple music
iPhone = i phone | eye phone
iPad = i pad | eye pad
MacBook = mac book
AirPods = air pods
Samsung = sam sung
OnePlus = one plus phone
Xiaomi = shao me | xiao mi
Wellfound = well found | wellfound
Y Combinator = y combinator | why combinator
Product Hunt = product hunt
Crunchbase = crunch base
Glassdoor = glass door
Naukri = naukri | nokri
Unstop = un stop
Duolingo = duo lingo
Valorant = valorant | valerant
"""),
    "startup": ("Startup and product terms", """
ICP = i c p
MNC = m n c
GTM = g t m | go to market strategy
PRD = p r d
MVP = m v p
PMF = p m f
OKR = o k r
OKRs = o k rs | o k r s
KPI = k p i
KPIs = k p is | k p i s
SaaS = sass product | saas | s a a s
B2B = b to b | b two b | b2b
B2C = b to c | b two c | b2c
D2C = d to c | d two c
ARR = a r r
MRR = m r r
CAC = c a c
LTV = l t v
ROI = r o i
NPS = n p s
DAU = d a u
MAU = m a u
GMV = g m v
SEO = s e o
CTA = c t a
A/B test = a b test | a slash b test
A/B testing = a b testing
PM = p m role
APM = a p m
PMs = p ms
CEO = c e o
CTO = c t o
CFO = c f o
COO = c o o
VP = v p of
HR = h r
QA = q a
TAM = t a m
SAM = s a m market
SOM = s o m
VC = v c funding | vc funding
VCs = v cs | v c s
LP = l p
ESOP = e sop | e s o p
ESOPs = e sops
Series A = series a
pre-seed = pre seed
roadmap = road map
user persona = user persona
north star metric = north star metric
JTBD = j t b d
GTM strategy = g t m strategy
stakeholder = stake holder
stakeholders = stake holders
onboarding = on boarding
churn = churn rate
cohort = co heart analysis
funnel = funnel analysis
"""),
    "india": ("Indian names and places", """
Bengaluru = bengal uru | bengal ooru | bangaluru
Gurugram = guru gram | gurugram
Gurgaon = gur gaon
Noida = noida | noyda
Hyderabad = hyder abad
Chennai = chen nai | chenai
Kolkata = kol kata | kolkatta
Mumbai = mum bai | mumbay
Pune = pune | poona city | poone
Ahmedabad = ahmed abad
Jaipur = jai pur
Lucknow = luck now city
Chandigarh = chandi garh
Kochi = ko chi
Thiruvananthapuram = thiru vananthapuram
Visakhapatnam = vizag city
Indore = in door city
Bhopal = bho pal
Nagpur = nag pur
Surat = sue rat
Delhi NCR = delhi n c r
IIT = i i t | i i t's
IITs = i i ts
IIM = i i m
IIMs = i i ms
NIT = n i t
BITS Pilani = bits pilani | bits pillani
Aadhaar = aadhar card | adhar card | aadhaar
PAN card = pan card
GST = g s t
INR = i n r
lakh = lac | lack rupees
lakhs = lacs
crore = crore | crores
Adarsh = adarsh | aadarsh
Lokendra = lukendra | lokendra
Aarav
Aditya
Ananya
Arjun
Ishaan
Kavya
Priya = priya | pria
Rahul
Rohan
Saanvi
Shreya
Vihaan
Vivek
Ankit
Manan = manan
Tejas
Saharsh = sahar sh
Siddharth = sid dharth
Harsh
Neha
Pooja
Sneha
Karthik = kartik | karthik
Srinivas = shrinivas
Venkatesh = venkat esh
Lakshmi = laxmi | lakshmi
Ganesh
Diwali = deewali | diwaali
Holi = holi festival
Namaste = namastay
ji = jee sir
Hinglish = hing lish | hin glish
"""),
    "shorthand": ("Shorthand", """
LGTM = l g t m | l.g.t.m.
FYI = f y i | f.y.i.
ASAP = a s a p | a.s.a.p.
ETA = e t a
EOD = e o d
EOW = e o w
BTW = b t w
TBH = t b h
IMO = i m o
IMHO = i m h o
WFH = w f h
OOO = o o o | out of office ooo
TL;DR = t l d r | tldr | t l dr
e.g. = e g | e.g | e. g.
i.e. = i e | i.e | i. e.
etc. = etcetera | et cetera
vs. = versus
AFAIK = a f a i k
IIRC = i i r c
ICYMI = i c y m i
DM = d m me | d m
DMs = d ms
TBD = t b d
TBC = t b c
WIP = w i p
POC = p o c
1:1 = one on one | one-on-one
Q&A = q and a | q n a
R&D = r and d | r n d
P&L = p and l
FAQ = f a q
FAQs = f a qs
PDF = p d f
PDFs = p d fs
"""),
}


# words that only make a heard form safe ("zoom call", not "zoom"): kept when swapping
CONTEXT = {"ai", "call", "meeting", "page", "doc", "app", "channel", "message", "file", "board",
           "task", "ticket", "mail", "sheet", "design", "video", "payment", "cab", "ride", "bike",
           "sim", "card", "festival", "city", "model", "cli", "server", "funding", "role", "rate",
           "analysis", "notebook", "cache", "product", "strategy", "of", "dataframe", "rupees", "sir",
           "prime", "phone", "motion", "pipeline", "repo", "query", "me", "market", "out", "office"}


def _written_for(form, written):
    """The heard form's text with the written word in place, keeping its context words."""
    words = form.split()
    lead = []
    while len(words) > 1 and words[0].lower() in CONTEXT and not written.lower().startswith(words[0].lower()):
        lead.append(words.pop(0))
    tail = []
    while len(words) > 1 and words[-1].lower() in CONTEXT and not written.lower().endswith(words[-1].lower()):
        tail.insert(0, words.pop())
    return " ".join(lead + [written] + tail)


def _parse(block):
    entries, words = [], []
    for line in block.strip().splitlines():
        written, _, heard = (part.strip() for part in line.partition("="))
        words.append(written)
        forms = [h.strip() for h in heard.split("|") if h.strip()]
        for form in forms:
            if form.lower() != written.lower():
                entries.append({"heard": form, "wanted": _written_for(form, written), "mode": "always"})
        if any(written.lower().startswith(f.lower()) and f.lower() != written.lower() for f in forms):
            # "e.g." itself must win over its own heard form "e.g"
            entries.append({"heard": written, "wanted": written, "mode": "always"})
        elif any(f.lower() == written.lower() for f in forms):
            # a case fix ("github" -> "GitHub")
            entries.append({"heard": written, "wanted": written, "mode": "always"})
    return entries, words


PARSED = {key: _parse(block) for key, (_, block) in GROUPS.items()}


class StarterWords:
    """The Starter words groups that are switched on. `yours` (your Dictionary) wins:
    a heard form you've defined yourself is left to it."""

    def __init__(self, enabled=None, yours=None):
        self.enabled = {key: (enabled or {}).get(key, True) for key in GROUPS}
        self.yours = yours

    def entries(self):
        mine = {e["heard"].lower() for e in self.yours.entries} if self.yours else set()
        mine |= {e["wanted"].lower() for e in self.yours.entries} if self.yours else set()
        return [e for key, on in self.enabled.items() if on for e in PARSED[key][0]
                if e["heard"].lower() not in mine]

    def apply(self, text):
        return swap(text, self.entries())

    def words(self):
        return sorted({w for key, on in self.enabled.items() if on for w in PARSED[key][1]})
