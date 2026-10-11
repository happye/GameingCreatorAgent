"""Import one explicit, immutable human zero-charge declaration; never call a model."""

import argparse
import json
import sys
from pathlib import Path

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.detail_billing_confirmation import import_billing_confirmation
from gamingcreator.infrastructure.detail_cost_history import refinement_cost_history


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--budget", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--material", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        confirmation = import_billing_confirmation(
            args.project,
            run_id=args.run,
            budget_id=args.budget,
            request_hash=args.request,
            attempt_no=args.attempt,
            material_path=args.material,
        )
        history = refinement_cost_history(args.project, args.run)
    except AppError as error:
        print(error.message, file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "runId": args.run,
                "requestHash": args.request,
                "attemptNo": args.attempt,
                "materialSha256": confirmation["materialSha256"],
                "humanBillingSummary": history["humanBillingSummary"],
                "sharedHumanBillingSummary": history["sharedHumanBillingSummary"],
                "newProviderCalls": 0,
                "sendBudgetUnchanged": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
