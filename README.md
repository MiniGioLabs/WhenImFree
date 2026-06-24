# 📅 CalenDate

> *Scheduling infrastructure for people who touch grass.*

An open-source, self-hosted scheduling platform inspired by [Cal.com](https://cal.com). Built for hosts who want to get paid, daters who want to propose plans, and friends who want to know where you're going.

---

## ✨ Why CalenDate?

Because your calendar should work **for** you, not against you.

| 🤔 You want... | 😤 Most tools... | 😎 CalenDate... |
|---|---|---|
| To set a 7–11 PM window | Split it into 15-min blocks | Shows the whole stripe |
| A date to propose "8–10 PM" | Blocked, sorry | ✅ Approved! Remainder stays open |
| To share the plan with friends | Screenshot your calendar | `/date/abc123` — done |
| Earnest deposits | 30% platform fee | Stripe Connect → goes to YOU |

---

## 🚀 Quick Start

```bash
git clone https://github.com/MiniGioLabs/calendate.git
cd calendate
uv sync
python3 -c "import secrets; open('.env','w').write('SECRET_KEY=*** + secrets.token_urlsafe(32))"
PYTHONPATH=src uv run uvicorn calendate.main:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000` → sign up → share your booking link.

---

## 🧠 How It Works

```
Host creates availability        Dater proposes a window
┌─────────────────────┐          ┌─────────────────────┐
│ 7 PM ──────── 11 PM │          │     8 PM – 10 PM     │
│                     │   ──➔    │   🍽️ Dinner          │
│                     │          │   📍 Café Luna       │
└─────────────────────┘          └─────────────────────┘
                  │
                  ▼
          Host approves
┌─────────────────────────────────────────┐
│  7–8 PM (open) │ 8–10 PM (Alex ✅) │ 10–11 PM (open) │
└─────────────────────────────────────────┘
                  │
                  ▼
         Friends see it at /date/abc123
```

---

## 🎯 Features

- 📅 **Apple Calendar-style dashboard** — stripes for all-day, dots for timed
- 🔗 **Cal.com-style booking page** — your personal `/book/your-name`
- 💸 **Stripe Connect** — deposits go directly to hosts (zero platform fees)
- ✂️ **Smart slot splitting** — approved times split, cancelled times merge back
- 📱 **SMS reminders** via Twilio — both parties get pinged
- 🔗 **Shareable date links** — `/date/{token}` for friends & family
- 🧹 **Clean code** — 12 modules, main.py under 100 lines

---

## 🏗️ Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+ / FastAPI |
| Frontend | htmx + Tailwind (server-rendered) |
| Database | SQLite (aiosqlite) |
| Payments | Stripe Connect |
| SMS | Twilio |
| Auth | bcrypt + signed sessions |

---

## 📁 Structure

```
src/calendate/
├── main.py              # Entry point
├── config.py            # Settings (env vars)
├── db.py                # SQLite + aiosqlite
├── auth.py              # bcrypt + phone auth
├── utils.py             # Templates, SMS, ICS
├── routers/
│   ├── auth.py          # Signup / login
│   ├── booking.py       # Public booking page
│   ├── dashboard.py     # Host dashboard + calendar
│   ├── slots.py         # Slot CRUD
│   └── requests.py      # Approve / deny / cancel
├── services/
│   └── calendar.py      # Calendar builder + slot split/merge
└── templates/
    ├── booking.html     # Cal.com-style booking UI
    └── dashboard.html   # Apple Calendar host view
```

---

## 🔧 Env Vars

| Variable | Required | What |
|---|---|---|
| `SECRET_KEY` | ✅ | For session cookies |
| `STRIPE_SECRET_KEY` | For deposits | Stripe API key |
| `TWILIO_*` | For SMS | Twilio account SID/token/phone |

---

## 🤝 Contributing

Built with ❤️ by [MiniGioLabs](https://github.com/MiniGioLabs). Issues and PRs welcome — especially if you find a bug before we do!

---

> *"Your calendar. Your rules. Your deposit."*
