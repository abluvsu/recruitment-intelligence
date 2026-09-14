# ⚡ Zero-Code Quickstart

> **For non-developer founders who have an AI coding agent subscription.**
> You don't need to know Python. Your AI agent will handle everything.

---

## What You Need

| Requirement | Where to get it |
|-------------|----------------|
| **Airtable account** with recruitment data | [airtable.com](https://airtable.com) |
| **Airtable API key** (Personal Access Token) | [airtable.com/create/tokens](https://airtable.com/create/tokens) — create a token with `data.records:read` scope |
| **Airtable Base ID** | Open your base → URL looks like `https://airtable.com/appXXXXXXXXXXXXXX/...` → the `appXXX...` part is your Base ID |
| **AI coding agent** (any one of these) | [Claude Code](https://docs.anthropic.com/en/docs/claude-code) · [Google Antigravity](https://cloud.google.com/antigravity) · [OpenAI Codex](https://github.com/openai/codex) · [Cursor](https://cursor.sh) |

### Expected Airtable Tables

Your Airtable base should have these tables (exact names):

| Table | Purpose |
|-------|---------|
| Departments | Company departments / teams |
| People | Hiring managers, recruiters, interviewers |
| Job Openings | Open positions |
| Candidates | People who applied |
| Applications | Individual applications linking candidates to jobs |
| Interviews | Scheduled/completed interviews |
| Offers | Formal offers extended |
| Findings | Optional: notes, flags, observations |

> **Don't have all 8 tables?** That's okay — the system handles missing tables gracefully and reports what data is available.

---

## Step-by-Step

### Step 1: Fork or Clone

**Option A — GitHub Fork (easiest)**
1. Click the **Fork** button at the top of this repository
2. You now have your own copy

**Option B — Clone**
```
git clone https://github.com/abluvsu/recruitment-intelligence.git
```

### Step 2: Open in Your AI Agent

Open your local copy in whichever AI coding agent you use:

| Agent | How to open |
|-------|------------|
| **Claude Code** | Open terminal in the project folder → type `claude` |
| **Google Antigravity (AGY)** | Open the folder as a workspace |
| **OpenAI Codex** | Open terminal in the project folder → type `codex` |
| **Cursor** | File → Open Folder → select the project folder |

### Step 3: Tell Your AI Agent What to Do

Copy and paste this prompt into your AI agent:

---

#### 🔑 First Time Setup Prompt

```
Set up this recruitment intelligence project for me:

1. Create a Python virtual environment and install the project dependencies
2. Create a .env file with these Airtable credentials:
   AIRTABLE_API_KEY=<PASTE YOUR API KEY HERE>
   AIRTABLE_BASE_ID=<PASTE YOUR BASE ID HERE>
3. Run the test suite to make sure everything works: python -m pytest -q
4. Tell me when it's ready
```

> ⚠️ **Replace** `<PASTE YOUR API KEY HERE>` and `<PASTE YOUR BASE ID HERE>` with your actual credentials before pasting.

---

#### 📊 Run the Pipeline Prompt

Once setup is confirmed, paste this:

```
Run the recruitment intelligence pipeline:

1. Pull a fresh snapshot from my Airtable (read-only, it won't change anything)
2. Run the full analytics pipeline on the snapshot
3. Show me the executive briefing from outputs/briefing.md
4. Summarize the top 3 findings and any urgent candidate actions
```

---

#### 🔄 Daily Briefing Prompt

For your daily standup, paste this each morning:

```
Run the recruitment pipeline with a fresh Airtable pull and show me
today's executive briefing. Highlight anything urgent.
```

---

## What You'll Get

After the pipeline runs, your AI agent will show you results like this:

### Executive Briefing (sample)

```
# Daily recruitment briefing

## What changed
- Profiled 39 records across 8 recruitment tables
- Leading source: 'Referral' ranked top by hire conversion yield
- Offer acceptance rate stands at 66.7%
- Primary hiring funnel bottleneck: offer → accepted stage

## Urgent items
- 5 active applications stalled for >= 14 days requiring review

## Candidate action queue
- cand-002 — escalate: Stalled in interview stage for 30+ days
- cand-005 — advance: Top interview score (4/5), advance to offer
- cand-008 — request feedback: Interview completed, awaiting scorecard
```

### Output Files

All outputs are saved in the `outputs/` folder:

| File | What it is |
|------|-----------|
| `briefing.md` | Your daily executive briefing (human-readable) |
| `briefing.html` | Same briefing as a web page |
| `briefing.json` | Full data with evidence blocks (for integrations) |
| `candidate_actions.json` | Every candidate recommendation with rationale |
| `findings.md` | Detailed findings memo |
| `memo.md` | One-page summary for sharing |

---

## Troubleshooting

| Problem | Tell your AI agent |
|---------|-------------------|
| "Module not found" errors | "Reinstall the project: `pip install -e .`" |
| Airtable connection fails | "Check my .env file — is the API key and base ID correct?" |
| Empty results | "Show me the Airtable snapshot to check if data was pulled correctly" |
| Want to run offline | "Run the pipeline using fixtures/clean_snapshot.json instead of Airtable" |

---

## Safety Notes

- ✅ **Your Airtable data is never modified** — the system only reads
- ✅ **Credentials stay local** — your `.env` file is git-ignored and never committed
- ✅ **Candidate actions are advisory only** — every recommendation says "human review required"
- ✅ **No automated rejections** — the system never recommends rejecting a candidate
- ✅ **Runs offline after first pull** — data is cached locally for repeat runs

---

## Need Help?

Paste this into your AI agent:

```
I'm having trouble with the recruitment-intelligence project.
Read the README.md and QUICKSTART.md, then help me debug my issue.
The error I'm seeing is: <describe your problem>
```

Your AI agent has full context from the project documentation and can diagnose most issues.
