# Portrait studio: the raw prompt, a running clock, a visible wait

- **See and edit the prompt** opens the whole prompt sent to Krea (the appearance words plus the house style wording) and the settings that go with it: checkpoint, style LoRA, ratio, mode and seed. It comes from `POST /library/portraits/prompt`, which builds the request exactly as painting does. Editing it marks it "Your own: sent exactly as written"; Generate then sends it with `raw: true` (no style wording added). "Back to the prompt from the appearance" undoes the edit; an unedited prompt follows the appearance as you type.
- **While painting** the current picture blurs, three rings turn over it, and a clock counts in tenths of a second (on the picture, in the line below and on the button). Motion stops for people who ask their system for reduced motion.
- Live on Mara (Krea, free): `painting.png` at 4.2 s, `painted.png` after 20.1 s. The settings line read "krea2Anime_v15_bf16 · style kreanima-lora-r32 · ratio 1:1 · fast mode"; portraits get no fixed seed, so it now says "a new seed each time".

Note: the new picture is in Mara's studio draft, not published; publish or remove it as you like.
