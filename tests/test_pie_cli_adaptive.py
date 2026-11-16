from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pie.interfaces import cli


def test_adaptive_cli_dispatches_to_runtime_function(tmp_path: Path):
    expected = {"context_state": "CURRENT", "content": "compact"}
    output = io.StringIO()
    with patch("pie.interfaces.cli.adaptive_context", return_value=expected) as adaptive:
        with redirect_stdout(output):
            code = cli.main(["adaptive", "needle", "--root", str(tmp_path)])
    assert code == 0
    adaptive.assert_called_once_with(
        tmp_path.resolve(),
        "needle",
        max_chars=12000,
        limit=8,
        mode="navigation",
        full_source_path=None,
    )
    assert json.loads(output.getvalue()) == expected
