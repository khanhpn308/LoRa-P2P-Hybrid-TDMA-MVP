#!/usr/bin/env bash
# Create/validate Gate field on GitHub Project #1, non-destructive.
set -euo pipefail
OWNER="khanhpn308"
PROJECT="1"
EXPECTED="G0: Scope,G1: RF,G2: Protocol,G3: Embedded,G4: Integration,G5: Security/Reliability,G6: Pilot Acceptance"
command -v gh >/dev/null || { echo "ERROR: install gh first"; exit 1; }
command -v python3 >/dev/null || { echo "ERROR: install python3 first"; exit 1; }
gh auth status >/dev/null || { echo "ERROR: gh auth login; gh auth refresh -s project"; exit 1; }

echo "Checking Gate field in Project #$PROJECT owned by $OWNER..."
FIELDS_JSON="$(gh project field-list "$PROJECT" --owner "$OWNER" --format json --limit 100)" || {
  echo "ERROR: cannot read Project fields. Try: gh auth refresh -s project"
  exit 1
}

# Exit 0 = matching, 3 = missing, 4 = existing but inconsistent.
set +e
printf '%s' "$FIELDS_JSON" | python3 -c '
import json,sys
data=json.load(sys.stdin)
matches=[f for f in data.get("fields",[]) if f.get("name")=="Gate"]
want=["G0: Scope","G1: RF","G2: Protocol","G3: Embedded",
      "G4: Integration","G5: Security/Reliability","G6: Pilot Acceptance"]
if not matches:
    print("MISSING: Gate")
    sys.exit(3)
if len(matches)!=1:
    print("MISMATCH: Multiple Gate fields")
    sys.exit(4)
field=matches[0]
got=[o.get("name") for o in field.get("options",[])]
if got==want and field.get("type","SingleSelect") in ("SingleSelect","SINGLE_SELECT"):
    print("VERIFIED: Gate already has the exact seven options")
    sys.exit(0)
print("MISMATCH: Gate differs from the canonical single-select field.")
print("Current type:",field.get("type"),"current options:",got)
sys.exit(4)
'
RESULT=$?
set -e
case "$RESULT" in
  0) exit 0 ;;
  3)
    echo "Creating Gate single-select..."
    gh project field-create "$PROJECT" --owner "$OWNER"       --name "Gate" --data-type "SINGLE_SELECT"       --single-select-options "$EXPECTED"
    ;;
  4)
    echo "STOP: Review the existing Gate field in the Project UI."
    exit 1
    ;;
  *)
    echo "ERROR: Could not inspect Gate configuration"
    exit 1
    ;;
esac

gh project field-list "$PROJECT" --owner "$OWNER" --format json --limit 100 |
  python3 -c '
import json,sys
matches=[f for f in json.load(sys.stdin).get("fields",[]) if f.get("name")=="Gate"]
want=["G0: Scope","G1: RF","G2: Protocol","G3: Embedded",
      "G4: Integration","G5: Security/Reliability","G6: Pilot Acceptance"]
assert len(matches)==1 and [o.get("name") for o in matches[0].get("options",[])]==want, "Gate not verified"
print("VERIFIED: GitHub Project Gate options G0-G6")
'
