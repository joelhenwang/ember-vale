"""Per attack turn: was there a foe left to hit (fight not yet won, hero up)?
Counts the hero's rolls against those turns only. Usage: python analyse.py run-N.json"""

import json
import sys

rows = json.load(open(sys.argv[1], encoding="utf-8"))
live = rolled = st = deeds = after_win = down = statuses = 0
for r in rows:
    won = False
    hero_down = False
    for t in r["turns"]:
        statuses += t["status"] != 200
        if t["attacks"]:
            if won and not t["encounters"]:
                after_win += 1
            elif hero_down:
                down += 1
            else:
                live += 1
                rolled += bool(t["hero_rolls"])
                st += bool(t["storyteller_hero_rolls"])
                deeds += t["deeds"]
                if not t["hero_rolls"]:
                    print("NO ROLL", r["scenario"], r["run"], t["turn"], t["attempt"][:50], "|", (t["prose"] or "")[:160])
        lines = " ".join(t["roll_lines"])
        if "Defeated" in lines:
            won = True
        if t["encounters"]:
            won = False
        if "->0 HP)" in lines and ("hits Wren" in lines):
            hero_down = True
        if "heals Wren" in lines:
            hero_down = False
print(json.dumps({
    "attack_turns_with_a_foe_up": live, "hero_rolled": rolled,
    "storyteller_tagged_hero": st, "from_deeds": deeds,
    "attack_turns_after_the_fight_was_won": after_win, "attack_turns_hero_down": down,
    "turns_refused": statuses,
}))
