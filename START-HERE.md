# Start here

You do not need to know any code. There is one thing to run.

---

## Step 1 — Get Python (once)

Python is the thing that runs the desk. Your computer may already have it.

**Mac:** open **Terminal** (press `Cmd + Space`, type `terminal`, hit Enter). Type this and press Enter:

```
python3 --version
```

If you see a number like `3.11.5`, you're done with this step. If you see an error, go to
[python.org/downloads](https://python.org/downloads), download it, and install it like any other app.

**Windows:** go to [python.org/downloads](https://python.org/downloads) and install it.
**On the first install screen, tick the box that says "Add Python to PATH."** This matters.

---

## Step 2 — Get the files (once)

On the GitHub page for this project, click the green **Code** button, then **Download ZIP**.
Unzip it. You'll get a folder called `CryptoHub`.

Put it somewhere you can find again — your Desktop is fine.

---

## Step 3 — Start it

**Mac:** double-click **`start.command`** inside that folder.

**Windows:** double-click **`start.bat`**.

*(If double-clicking does nothing: open Terminal or Command Prompt, type `cd `, then drag
the CryptoHub folder onto the window and press Enter. Then type `python3 start.py` on Mac,
or `python start.py` on Windows.)*

A black window opens and prints some lines. **Leave that window open** — closing it stops
the desk. The first time takes about a minute while it downloads what it needs.

Your browser will open by itself and show the dashboard.

That's it. It's running.

---

## What you're looking at

The top line tells you in plain English what's happening. Something like:

> You started with $100.00. You now have $109.21 — up $9.21.
> This is practice money — nothing real is at risk.

**It starts in practice mode.** No real money. It uses pretend dollars against real
market prices, so you can watch it for a few days and see how it actually behaves
before deciding anything.

Three buttons, top right:

| Button | What it does |
|---|---|
| **Settings** | Change how much, how careful, which coins, practice or real |
| **Pause** | Stops it buying anything new. It still sells things it already owns. |
| **Flatten all** | Sells everything, right now |

The row of ten boxes is the committee. Each one checks a different thing and any
one of them can refuse a coin. The **Activity** list underneath shows who refused
what and why — that's how you learn what it's actually doing.

---

## To stop it

Click into the black window and press **Ctrl + C**. Or just close the window.
Your history is saved; next time you start it, it picks up where it left off.

---

## Using real money

**Don't do this yet.** Watch it in practice mode for a week first. You will learn more
from that week than from anything I can write here.

When you do:

1. **Make a brand-new wallet.** Not one you already use. A fresh one, for this only.
2. **Put in only what you would genuinely shrug at losing.** Not "money I'd rather not
   lose." Money you would forget about.
3. In the dashboard, click **Settings** → **Real money** → paste that new wallet's key →
   **Save**.
4. Stop the desk and start it again.

### Keeping other people out

The dashboard now requires an access key that changes every time you start the
desk. It is in the link that opens automatically — you never type it. Websites
you visit can no longer touch the desk, which was possible in an earlier version.

Worth knowing: **the desk cannot send your money anywhere.** It has no transfer or
withdraw function at all — it only swaps coins back to SOL or BNB inside your own
wallet. So even if someone got into the dashboard, they could annoy you by selling
your positions, but they could not take the money.

What they *could* take is the key file. Which is why:

### About the wallet key

The key is a long line of letters and numbers. **That text is the money.** It is not a
password you can reset. Anyone who gets it can empty the wallet, in seconds, and nothing
can undo it.

So:

- It gets saved in a file called `.env` in the folder. That file *is* your wallet.
- Keep the desk folder **out of Dropbox, iCloud, OneDrive and Google Drive.** A key
  in a synced folder is a key on someone else's servers. The desk checks this and
  refuses to trade for real if it finds one.
- Never send it to anyone. Never paste it into a chat, an email, or a website.
  Not to me, not to "support", not to anyone who offers to help you set this up.
- Nobody legitimate will ever ask you for it. Anyone who does is stealing from you.

---

## The part I'd rather you knew going in

I built what you asked for and it does what it says. But you should know what the
numbers say before you put real money in it.

Run this once — in the black window, press Ctrl+C first, then type:

```
python3 start.py plan
```

It prints the actual arithmetic. The short version:

**A $100 account can only fall about 25% before it cannot trade at all.** Not "before
it's in trouble" — before it's *finished*. Each trade has a minimum size (fees and
network costs make anything smaller pointless), and below about $75 the desk can't
place even the smallest valid trade. In simulation, about 97 runs out of 100 end
exactly there.

That is not a flaw in the desk or a setting you can change. It's arithmetic about the
account size. The two things that genuinely move it:

- **More starting money.** Around $450 is where the smallest possible trade stops
  being an oversized bet.
- **Watching it in practice first.** After a few hundred practice trades you have your
  *own* numbers instead of my assumptions, and `plan` will use them.

The viral screenshot that probably brought you here claimed $11,345 from $52. Its own
dashboard, in the same image, showed **+$8.70**. Both numbers were on screen at once.
That is roughly what this kind of thing actually returns on a good day.

---

## If something breaks

| What you see | What to do |
|---|---|
| `python: command not found` | Python isn't installed, or the PATH box wasn't ticked on Windows. Redo Step 1. |
| The window flashes and closes | Open Terminal / Command Prompt and run it from there (see Step 3) so you can read the error. |
| It says real-money mode isn't ready | Open the dashboard and click **Switch back to practice mode**. If the dashboard won't open at all, run `python3 start.py --paper`. |
| It won't start after changing a setting | `python3 start.py --paper` puts it back to practice. Nothing is lost. |
| Changing the budget seems to do nothing | Fixed. In practice mode it now applies immediately and restarts the practice account at the new amount, clearing the old history. |
| `Address already in use` | An older copy is still running. It now picks the next free port by itself and tells you which. |
| `No pairs returned by any feed` | Your internet is down, or a firewall is blocking it. |
| Browser says it can't connect | The black window probably closed. Start it again. |
| Nothing is being bought | Normal. It refuses most coins. Check the Activity list to see why. |

Anything else: copy what the black window says and ask. Copy the text — **never a
screenshot showing your `.env` file or a wallet key.**
