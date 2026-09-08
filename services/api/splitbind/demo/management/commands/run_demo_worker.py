import math
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from splitbind.demo.worker import reconcile_stale_jobs, run_worker_cycle
from splitbind.uploads import services as upload_services


class Command(BaseCommand):
    help = "Run the local/offline SplitBind demo worker."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=0.5)

    def handle(self, *args, **options):
        if not settings.SPLITBIND_DEMO_MODE:
            raise CommandError("DEMO_MODE_DISABLED")
        poll_interval = options["poll_interval"]
        if not math.isfinite(poll_interval) or not 0.1 <= poll_interval <= 5.0:
            raise CommandError("DEMO_POLL_INTERVAL_INVALID")
        try:
            storage = upload_services.get_storage()
        except KeyboardInterrupt:
            self.stdout.write("action=stopped code=INTERRUPTED")
            return
        except Exception:
            raise CommandError("DEMO_STORAGE_UNAVAILABLE") from None
        try:
            recovered = reconcile_stale_jobs(storage=storage)
        except KeyboardInterrupt:
            self.stdout.write("action=stopped code=INTERRUPTED")
            return
        except Exception:
            raise CommandError("DEMO_STALE_RECOVERY_FAILED") from None
        for outcome in recovered:
            action = "recovered" if outcome.safe_code == "OK" else "recovery"
            self.stdout.write(
                f"action={action} job={outcome.job_id} "
                f"kind={outcome.kind} code={outcome.safe_code}"
            )
        try:
            while True:
                try:
                    result = run_worker_cycle(storage=storage)
                except Exception:
                    self.stdout.write("action=cycle code=DEMO_WORKER_CYCLE_FAILED")
                    if options["once"]:
                        return
                    time.sleep(poll_interval)
                    continue
                if result is not None:
                    action = "processed" if result.safe_code == "OK" else "failed"
                    self.stdout.write(
                        f"action={action} job={result.job_id} "
                        f"kind={result.kind} code={result.safe_code}"
                    )
                if options["once"]:
                    return
                if result is None:
                    time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stdout.write("action=stopped code=INTERRUPTED")
