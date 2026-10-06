#!/bin/bash
# Rebuild the ModelCar columns in model-list.csv from the registry.
#
# Red Hat's "Validated models" documentation tables undercount what is actually
# published. Two earlier passes each found more than the last:
#
#   docs tables ................................. 48 of 135
#   registry, modelcar-<model> + bare <model> .... 95
#   registry, all three naming conventions ...... 127   <- this script
#
# The three conventions are NOT interchangeable. A path that looks obviously
# right can 404 while the same model exists under another form:
#
#   rhelai1/modelcar-<model>:1.5            (also :1.4)
#   rhai/modelcar-<model>:3.0
#   rhai/modelcar-<org>-<model>:3.0
#
# rhai also serves every repo without the modelcar- prefix, under both :1.5 and
# :3.0, plus build-stamped tags (:3.0-1782241594) and :latest.
#
#   ./hack/probe-modelcars.sh            # probe and report, no writes
#   ./hack/probe-modelcars.sh --write    # also update the CSVs
#
# Needs skopeo and credentials for registry.redhat.io in podman's default
# search path. Reads nothing but manifests - no images are pulled.
#
# Concurrency is deliberately low (-P 6) and every negative is retried three
# times with backoff. registry.redhat.io rate-limits, and a throttled request
# looks exactly like a 404 here, so an aggressive run reports models as missing
# that actually exist. A slow correct answer beats a fast wrong one.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CSV="${ROOT}/model-list.csv"
WRITE=0
[[ "${1:-}" == "--write" ]] && WRITE=1
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT

command -v skopeo >/dev/null || { echo "error: skopeo not found" >&2; exit 1; }
[[ -f "$CSV" ]] || { echo "error: $CSV not found" >&2; exit 1; }

# ---- candidate paths, all three conventions
python3 - "$CSV" <<'PY' > "$WORK/cand.tsv"
import csv, re, sys
def norm(x):
    return re.sub(r'-+','-', x.lower().replace('.','-').replace('_','-')).strip('-')
seen=set()
for r in csv.DictReader(open(sys.argv[1])):
    hf=r['hf_repo'].strip()
    if not hf: continue
    org,name = hf.split('/',1) if '/' in hf else ('',hf)
    o,n = norm(org), norm(name)
    names={n}
    if n.startswith('meta-'): names.add(n[5:])
    if o: names.add(f'{o}-{n}')
    for base in names:
        for pre in ('modelcar-',''):
            for ns,tags in (('rhai',('3.0','1.5')),('rhelai1',('1.5','1.4'))):
                for t in tags:
                    p=f'registry.redhat.io/{ns}/{pre}{base}:{t}'
                    if (r['model'],p) in seen: continue
                    seen.add((r['model'],p))
                    print(f"{r['model']}\t{p}")
PY
echo "probing $(wc -l < "$WORK/cand.tsv") candidate paths..."

# A negative is only trusted after retries: registry.redhat.io rate-limits, and
# a throttled request is indistinguishable from a 404 at this level. Probing at
# high concurrency without this produces false "does not exist" results.
cat > "$WORK/hit.sh" <<'EOF'
#!/bin/bash
m="${1%%$'\t'*}"; img="${1##*$'\t'}"
for attempt in 1 2 3; do
  if skopeo inspect --raw "docker://$img" >/dev/null 2>&1; then
    printf '%s\t%s\n' "$m" "$img"; exit 0
  fi
  [ "$attempt" -lt 3 ] && sleep $(( attempt * 2 ))
done
exit 0
EOF
chmod +x "$WORK/hit.sh"
xargs -a "$WORK/cand.tsv" -d'\n' -I{} -P 6 "$WORK/hit.sh" {} 2>/dev/null > "$WORK/hits.tsv"
echo "  $(wc -l < "$WORK/hits.tsv") hits across $(cut -f1 "$WORK/hits.tsv" | sort -u | wc -l) models"

# ---- one canonical path per model: prefer modelcar- prefix, :3.0, rhai, shortest
python3 - "$WORK/hits.tsv" <<'PY' > "$WORK/chosen.tsv"
import collections, sys
def rank(img):
    name=img.split('/')[-1]; ns=img.split('/')[1]; tag=name.rsplit(':',1)[1]
    return (0 if name.startswith('modelcar-') else 1,
            {'3.0':0,'1.5':1,'1.4':2}.get(tag,9),
            {'rhai':0,'rhelai1':1}.get(ns,9), len(name))
by=collections.defaultdict(list)
for line in open(sys.argv[1]):
    m,img=line.rstrip('\n').split('\t'); by[m].append(img)
for m,imgs in by.items():
    print(f"{m}\t{sorted(set(imgs),key=rank)[0]}")
PY

# ---- compressed size + architectures, amd64 entry for multi-arch indexes
cat > "$WORK/meta.sh" <<'EOF'
#!/bin/bash
m="${1%%$'\t'*}"; img="${1##*$'\t'}"; repo="${img%:*}"
raw=$(skopeo inspect --raw "docker://$img" 2>/dev/null)
[ -z "$raw" ] && { printf '%s\t%s\t\t\n' "$m" "$img"; exit; }
printf '%s' "$raw" | python3 -c "
import sys,json,subprocess
m='''$m'''; img='''$img'''; repo='''$repo'''
try: d=json.load(sys.stdin)
except Exception: print(f'{m}\t{img}\t\t'); sys.exit()
if 'manifests' in d:
    ar=sorted({x.get('platform',{}).get('architecture','?') for x in d['manifests'] if x.get('platform',{}).get('os')!='unknown'})
    dig=next((x['digest'] for x in d['manifests'] if x.get('platform',{}).get('architecture')=='amd64'),None)
    if dig: d=json.loads(subprocess.run(['skopeo','inspect','--raw','docker://'+repo+'@'+dig],capture_output=True,text=True).stdout)
else: ar=['amd64']
print(f\"{m}\t{img}\t{sum(l.get('size',0) for l in d.get('layers',[]))/1e9:.1f}\t{','.join(ar)}\")
"
EOF
chmod +x "$WORK/meta.sh"
xargs -a "$WORK/chosen.tsv" -d'\n' -I{} -P 6 "$WORK/meta.sh" {} 2>/dev/null > "$WORK/meta.tsv"

python3 - "$CSV" "$WORK/meta.tsv" "$WRITE" <<'PY'
import csv, sys
csv_path, meta_path, write = sys.argv[1], sys.argv[2], sys.argv[3]=='1'
live={}
for line in open(meta_path):
    p=line.rstrip('\n').split('\t')
    if len(p)==4 and p[2]: live[p[0]]=(p[1],p[2],p[3])
rows=list(csv.DictReader(open(csv_path)))
added=changed=0
for r in rows:
    hit=live.get(r['model'])
    if not hit: continue
    new,gb,arch=hit
    if not r['redhat_modelcar']: added+=1
    elif r['redhat_modelcar']!=new: changed+=1
    if write: r['redhat_modelcar'],r['modelcar_gb'],r['modelcar_arch']=new,gb,arch
sup=[r for r in rows if r['support_level'] in ('Enabled','Validated')]
print(f"  would add {added}, repath {changed}" if not write else f"  added {added}, repathed {changed}")
print(f"  coverage: {len(live)}/{len(rows)} all rows | "
      f"{sum(1 for r in sup if r['model'] in live)}/{len(sup)} buildable")
missing=[r['model'] for r in rows if r['model'] not in live]
if missing:
    print("  no ModelCar:")
    for m in missing: print(f"    {m}")
if write:
    cols=list(rows[0].keys())
    for path,subset in ((csv_path,rows), (csv_path.replace('model-list.csv','model-list-supported.csv'),sup)):
        with open(path,'w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(subset)
    print("  CSVs updated")
PY
