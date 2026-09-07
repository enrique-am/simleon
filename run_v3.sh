#!/bin/sh
# SimLeón v3 runner — quota-aware, resumable. Exits 75 when the daily image cap is spent.
# Steps are idempotent: restyle skips squares already restyled, detect/refine/seams skip done jobs.
cd /root/simleon
export NB_DAILY_BUDGET=${NB_DAILY_BUDGET:-240}
pgrep -f "http.server 8765" >/dev/null || (setsid nohup python3 -m http.server 8765 --bind 127.0.0.1 >/tmp/http.log 2>&1 </dev/null &)
sleep 2
say(){ echo "== $1 $(date -u +%H:%M) [quota $(python3 -c "import sys;sys.path.insert(0,'gen');import pixelate as P;print(P.quota_used(),'/',P.DAILY_BUDGET)")]"; }

EXIST=$(python3 -c "
import json
g=json.load(open('grid.json'))
print(';'.join(f\"{s['i']},{s['j']}\" for s in g['squares'] if -2<=s['j']<=4 and not (s['i']==-1 and s['j']==1)))")
say "restyle existing"
python3 gen/restyle.py --std=-1,1 --only="$EXIST" --n 2 --max-n 3 --min-judge 6.5 --min-style 7 || [ $? -ne 75 ] || exit 75

NORTH=$(python3 -c "
import json,os
g=json.load(open('grid.json'))
print(';'.join(f\"{s['i']},{s['j']}\" for s in g['squares'] if s['j']>=5 and os.path.exists(f\"renders/sq_{s['i']}_{s['j']}.png\")))")
if [ -n "$NORTH" ]; then
  say "restyle north"
  python3 gen/restyle.py --std=-1,1 --only="$NORTH" --n 2 --max-n 3 --min-judge 6.5 --min-style 7 || [ $? -ne 75 ] || exit 75
fi

say "detect"
[ -f build/refine_queue_v3.json ] || python3 gen/detect.py --out build/refine_queue_v3.json --min-sev 4
say "refine"
python3 gen/refine.py --queue build/refine_queue_v3.json || [ $? -ne 75 ] || exit 75

say "seam audit"
[ -f build/seams.json ] || python3 gen/seams.py audit --out build/seams.json
say "seam repair"
python3 gen/seams.py repair --queue build/seams.json --min 5 || [ $? -ne 75 ] || exit 75

say "build"
python3 build/build_tiles.py --in pixels_pro --out site --grid 2048 --tile-format webp --tile-quality 75 --embed-grid 512 --embed-quality 68 --normalize 0.6
python3 build/build_site.py --artifact-story-url https://claude.ai/code/artifact/6eee3f4a-5d22-4fb2-b17a-0f9924173645 --hires-url https://enrique-am.github.io/simleon/
python3 build/build_story.py https://claude.ai/code/artifact/e6a51c1d-4690-4622-8356-a39b4a2e5922 https://enrique-am.github.io/simleon/
echo "== ALL DONE $(date -u)"
