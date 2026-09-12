import math
import time

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from splitbind.observability import get_logger, log_swallowed
from splitbind.release.worker import (
    process_integrity_cycle,
    recover_stale_integrity_jobs,
    validate_integrity_worker_startup,
)
from splitbind.uploads import services as upload_services


logger = get_logger("splitbind.release.run_integrity_worker")


class Command(BaseCommand):
    help = "Run the bounded SplitBind integrity-release worker."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=1.0)

    def handle(self, *args, **options):
        poll_interval = options["poll_interval"]
        if not math.isfinite(poll_interval) or not 0.1 <= poll_interval <= 5.0:
            raise CommandError("INTEGRITY_POLL_INTERVAL_INVALID")
        try:
            validate_integrity_worker_startup()
        except ImproperlyConfigured as error:
            raise CommandError(str(error)) from None
        try:
            storage = upload_services.get_storage()
        except Exception as error:
            log_swallowed(logger, error, action="startup", code="INTEGRITY_STORAGE_UNAVAILABLE")
            raise CommandError("INTEGRITY_STORAGE_UNAVAILABLE") from None
        try:
            recovered = recover_stale_integrity_jobs(storage=storage, now=timezone.now())
        except Exception as error:
            log_swallowed(logger, error, action="startup", code="INTEGRITY_STALE_RECOVERY_FAILED")
            raise CommandError("INTEGRITY_STALE_RECOVERY_FAILED") from None
        for outcome in recovered:
            self.stdout.write(
                f"action=recovery job={outcome.job_id} kind={outcome.kind} code={outcome.safe_code}"
            )
        try:
            while True:
                try:
                    result = process_integrity_cycle(storage, timezone.now())
                except Exception as error:
                    log_swallowed(
                        logger, error, action="cycle", code="INTEGRITY_WORKER_CYCLE_FAILED"
                    )
                    self.stdout.write(
                        "action=cycle code=INTEGRITY_WORKER_CYCLE_FAILED"
                    )
                    if options["once"]:
                        return
                    time.sleep(poll_interval)
                    continue
                if result is not None:
                    action = "processed" if result.safe_code == "OK" else "failed"
                    self.stdout.write(
                        f"action={action} job={result.job_id} kind={result.kind} code={result.safe_code}"
                    )
                if options["once"]:
                    return
                if result is None:
                    time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stdout.write("action=stopped code=INTERRUPTED")
