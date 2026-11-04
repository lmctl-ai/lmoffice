#!/usr/bin/env bash
#!/usr/bin/env bash
# Only the public qualification workflow may publish a candidate as Latest.
set -euo pipefail
python3 "$(dirname "$0")/manage-qualified-draft.py" promote "$@"
