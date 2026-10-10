"""Sum up long_run.py output: fights, rolls, health, levels, rests, time."""
import json
import statistics
import sys

for r in json.load(open(sys.argv[1], encoding="utf-8")):
    t = r["turns"]
    secs = [x["seconds"] for x in t if x["status"] == 200]
    print(f"== story {r['run']} ({len(t)} turns played, ${r['spend_usd']})")
    print(f"   seconds/turn median {statistics.median(secs):.1f}, max {max(secs):.1f}")
    enc = [(x["turn"], l) for x in t for l in x["rolls"] if l.startswith("Encounter")]
    print("   encounters:", enc)
    for x in t:
        party = " ".join(f"{m['name']}:L{m['level']} {m['hp_current']}/{m['hp_max']} xp{m['xp']}" for m in x["party"])
        foes = ",".join(f"{n}:{h}" for n, h in x["foes"])
        ash = "; ".join(f"{a[1]} {a[2][:40]}" for a in x["ash_chose"])
        unres = sum(int(f.get("unresolved", "0")) for f in x["fight"])
        print(f"   T{x['turn']:>2} d{x['day']} {x['phase']:<9} {x['kind']:<4} st{x['status']} {x['seconds']:>5}s | {party} | foes[{foes}] | rolls {len(x['rolls'])} unres {unres} | ash: {ash}")
    rolls = [l for x in t for l in x["rolls"]]
    print("   rolls by kind:", {k: sum(1 for l in rolls if l.startswith(k)) for k in ("Wren", "Ash", "Goblin", "Encounter", "Defeated", "Level", "Settled")})
    print("   settled rumours at the end:", t[-1]["settled"], "| open:", t[-1]["rumours"][:4])
