#!/usr/bin/env bash
# WAVE 1 (post-rebaseline): link only #8–#12, #14–#16 to Project #1 and set Gate.
# Does NOT create issues, edit Issue bodies, alter labels, change assignees or delete Project data.
# Safe to rerun after interruption; uses existing Project item when already present.
set -euo pipefail

OWNER="khanhpn308"
REPO="khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP"
PROJECT="1"
BASE="https://github.com/$REPO/issues"
command -v gh >/dev/null || { echo "ERROR: GitHub CLI missing"; exit 1; }
command -v python3 >/dev/null || { echo "ERROR: python3 missing"; exit 1; }
gh auth status -h github.com >/dev/null || { echo "ERROR: login first"; exit 1; }

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# Confirm Project, Gate and all expected issue titles before any mutation.
gh project view "$PROJECT" --owner "$OWNER" --format json > "$TMP_DIR/project.json"
gh project field-list "$PROJECT" --owner "$OWNER" --format json --limit 100 > "$TMP_DIR/fields.json"
gh project item-list "$PROJECT" --owner "$OWNER" --format json --limit 500 > "$TMP_DIR/items.json"

PROJECT_ID="$(python3 - "$TMP_DIR/project.json" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1],encoding="utf-8"))
assert obj.get("id"),"Missing Project node ID"
print(obj["id"])
PY
)"
GATE_FIELD_ID="$(python3 - "$TMP_DIR/fields.json" <<'PY'
import json,sys
fields=json.load(open(sys.argv[1],encoding="utf-8")).get("fields",[])
want=["G0: Scope","G1: RF","G2: Protocol","G3: Embedded","G4: Integration","G5: Security/Reliability","G6: Pilot Acceptance"]
matches=[x for x in fields if x.get("name")=="Gate"]
assert len(matches)==1 and [o.get("name") for o in matches[0].get("options",[])]==want,"Gate must have exact G0–G6 options"
print(matches[0]["id"])
PY
)"
option_id() {
  python3 - "$TMP_DIR/fields.json" "$1" <<'PY'
import json,sys
fields=json.load(open(sys.argv[1],encoding="utf-8")).get("fields",[])
field=next(x for x in fields if x.get("name")=="Gate")
opt=next(x for x in field["options"] if x["name"]==sys.argv[2])
print(opt["id"])
PY
}
existing_item_id() {
  python3 - "$TMP_DIR/items.json" "$1" <<'PY'
import json,sys
items=json.load(open(sys.argv[1],encoding="utf-8")).get("items",[])
url=sys.argv[2].rstrip("/")
for item in items:
    content=item.get("content") or {}
    item_url=content.get("url") or item.get("url") or ""
    if item_url.rstrip("/")==url:
        print(item.get("id",""))
        break
PY
}

while IFS='|' read -r n code; do
  [ -n "$n" ] || continue
  title="$(gh issue view "$n" -R "$REPO" --json title --jq '.title')"
  case "$title" in
    "[W1-$code]"*) ;;
    *) echo "ERROR: Issue #$n unexpected title: $title"; exit 1 ;;
  esac
done <<'ISSUE_CHECK'
8|01
9|02
10|03
11|04
12|05
14|07
15|08
16|09
ISSUE_CHECK

echo "Preflight PASS: 12 actual Issues and canonical Gate field."
declare -i changed=0
while IFS='|' read -r number gate; do
  [ -n "$number" ] || continue
  url="$BASE/$number"
  item_id="$(existing_item_id "$url")"
  if [ -z "$item_id" ]; then
    echo "Linking #$number to Project $PROJECT..."
    added="$(gh project item-add "$PROJECT" --owner "$OWNER" --url "$url" --format json)"
    item_id="$(python3 -c 'import sys,json
try:
  v=json.load(sys.stdin)
  print(v.get("id","") or v.get("item",{}).get("id",""))
except (ValueError,AttributeError):
  print("")
' <<< "$added")"
    if [ -z "$item_id" ]; then
      gh project item-list "$PROJECT" --owner "$OWNER" --format json --limit 500 > "$TMP_DIR/items.json"
      item_id="$(existing_item_id "$url")"
    fi
    if [ -z "$item_id" ]; then
      echo "ERROR: Unable to locate Project item ID for #$number"
      exit 1
    fi
  else
    echo "Existing Project item for #$number: $item_id"
  fi
  oid="$(option_id "$gate")"
  gh project item-edit --id "$item_id" --project-id "$PROJECT_ID" --field-id "$GATE_FIELD_ID" --single-select-option-id "$oid" >/dev/null
  got="$(gh api graphql -f query='query($item:ID!){ node(id:$item){ ... on ProjectV2Item { fieldValueByName(name:"Gate"){ ... on ProjectV2ItemFieldSingleSelectValue { name } } } } }' -F item="$item_id" --jq '.data.node.fieldValueByName.name')"
  if [ "$got" != "$gate" ]; then echo "ERROR: #$number Gate got=$got expected=$gate"; exit 1; fi
  echo "VERIFIED: Issue #$number belongs to Project #$PROJECT, Gate=$gate"
  changed+=1
done <<'ISSUE_GATES'
8|G0: Scope
9|G1: RF
10|G1: RF
11|G1: RF
12|G2: Protocol
14|G2: Protocol
15|G4: Integration
16|G4: Integration
ISSUE_GATES

[ "$changed" -eq 8 ] || { echo "ERROR: only $changed / 8 processed"; exit 1; }
echo "SUCCESS: 8/8 Wave 1 Issues linked and Gate VERIFIED on GitHub Project #1."
echo "NOTE: Priority, Status, Sprint, Estimate, owners are NOT automatically modified."
